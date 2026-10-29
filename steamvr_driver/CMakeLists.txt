cmake_minimum_required(VERSION 3.16)
project(eyetrackvr_steamvr_driver CXX)

# Builds the SteamVR driver folder (eyetrackvr/) with the binary in bin/win64 or bin/linux64.
#   cmake -S steamvr_driver -B build/steamvr_driver -DCMAKE_BUILD_TYPE=Release
#   cmake --build build/steamvr_driver --config Release
# Register the output folder with: vrpathreg adddriver <build>/eyetrackvr

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "SteamVR drivers are 64-bit only")
endif()

if(WIN32)
  set(ETVR_PLATFORM win64)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
  set(ETVR_PLATFORM linuxarm64)
else()
  set(ETVR_PLATFORM linux64)
endif()

set(ETVR_DRIVER_DIR ${CMAKE_BINARY_DIR}/eyetrackvr)

add_library(driver_eyetrackvr SHARED
  src/driver_main.cpp
  src/hmd_shim.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk/cpp/gaze_source.cpp
)
target_include_directories(driver_eyetrackvr PRIVATE
  src
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk/cpp
)
target_include_directories(driver_eyetrackvr SYSTEM PRIVATE third_party/openvr)
set_target_properties(driver_eyetrackvr PROPERTIES
  PREFIX ""
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
  RUNTIME_OUTPUT_DIRECTORY ${ETVR_DRIVER_DIR}/bin/${ETVR_PLATFORM}
  LIBRARY_OUTPUT_DIRECTORY ${ETVR_DRIVER_DIR}/bin/${ETVR_PLATFORM}
)
foreach(config Debug Release RelWithDebInfo MinSizeRel)
  string(TOUPPER ${config} CONFIG)
  set_target_properties(driver_eyetrackvr PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_${CONFIG} ${ETVR_DRIVER_DIR}/bin/${ETVR_PLATFORM}
    LIBRARY_OUTPUT_DIRECTORY_${CONFIG} ${ETVR_DRIVER_DIR}/bin/${ETVR_PLATFORM})
endforeach()

if(MSVC)
  target_compile_options(driver_eyetrackvr PRIVATE /W4 /permissive-)
  # No VC++ redistributable needed on the user's PC.
  set_property(TARGET driver_eyetrackvr PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
else()
  target_compile_options(driver_eyetrackvr PRIVATE -Wall -Wextra)
  # SteamVR runs inside the Steam Linux Runtime; don't depend on the host's libstdc++.
  # --exclude-libs keeps that static libstdc++ out of the export table, so it can't interpose
  # on vrserver's own; only HmdDriverFactory is exported.
  target_link_options(driver_eyetrackvr PRIVATE -static-libstdc++ -static-libgcc -Wl,--no-undefined -Wl,--exclude-libs,ALL)
endif()

option(ETVR_DRIVER_TESTS "Build the fake vrserver used to test the driver without SteamVR" OFF)
if(ETVR_DRIVER_TESTS)
  add_executable(fake_vrserver tests/fake_vrserver.cpp)
  target_include_directories(fake_vrserver SYSTEM PRIVATE third_party/openvr)
  if(NOT WIN32)
    target_link_libraries(fake_vrserver PRIVATE ${CMAKE_DL_LIBS} pthread)
  endif()
endif()

add_custom_command(TARGET driver_eyetrackvr POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_directory ${CMAKE_CURRENT_SOURCE_DIR}/eyetrackvr ${ETVR_DRIVER_DIR}
)
