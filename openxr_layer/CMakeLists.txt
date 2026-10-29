cmake_minimum_required(VERSION 3.16)
project(eyetrackvr_openxr_layer CXX)

# Builds the OpenXR API layer folder (eyetrackvr_openxr_layer/): the layer library plus its
# manifest, which points at the library by relative path.
#   cmake -S openxr_layer -B build/openxr_layer -DCMAKE_BUILD_TYPE=Release
#   cmake --build build/openxr_layer --config Release
# EyeTrackVR installs the manifest as an implicit layer while "Foveated rendering gaze" is on.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(ETVR_LAYER_NAME XR_APILAYER_EYETRACKVR_eye_gaze)
set(ETVR_LAYER_DIR ${CMAKE_BINARY_DIR}/eyetrackvr_openxr_layer)
if(WIN32)
  set(ETVR_LAYER_FILE ${ETVR_LAYER_NAME}.dll)
else()
  set(ETVR_LAYER_FILE lib${ETVR_LAYER_NAME}.so)
endif()

add_library(${ETVR_LAYER_NAME} SHARED
  src/layer.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk/cpp/gaze_source.cpp
)
target_include_directories(${ETVR_LAYER_NAME} PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk
  ${CMAKE_CURRENT_SOURCE_DIR}/../sdk/cpp
)
target_include_directories(${ETVR_LAYER_NAME} SYSTEM PRIVATE third_party/openxr)
# Everything is called through the next layer's function pointers, never the loader directly.
target_compile_definitions(${ETVR_LAYER_NAME} PRIVATE XR_NO_PROTOTYPES _CRT_SECURE_NO_WARNINGS)
set_target_properties(${ETVR_LAYER_NAME} PROPERTIES
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
  RUNTIME_OUTPUT_DIRECTORY ${ETVR_LAYER_DIR}
  LIBRARY_OUTPUT_DIRECTORY ${ETVR_LAYER_DIR}
)
foreach(config Debug Release RelWithDebInfo MinSizeRel)
  string(TOUPPER ${config} CONFIG)
  set_target_properties(${ETVR_LAYER_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_${CONFIG} ${ETVR_LAYER_DIR}
    LIBRARY_OUTPUT_DIRECTORY_${CONFIG} ${ETVR_LAYER_DIR})
endforeach()

if(MSVC)
  target_compile_options(${ETVR_LAYER_NAME} PRIVATE /W4 /permissive-)
  set_property(TARGET ${ETVR_LAYER_NAME} PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
else()
  # {XR_TYPE_...} with the rest zeroed is the usual OpenXR idiom.
  target_compile_options(${ETVR_LAYER_NAME} PRIVATE -Wall -Wextra -Wno-missing-field-initializers)
  # Loaded into arbitrary games: don't depend on, or interpose on, their libstdc++. The version
  # script exports the loader entry point only (std:: templates are default-visibility otherwise).
  target_link_options(${ETVR_LAYER_NAME} PRIVATE -static-libstdc++ -static-libgcc -Wl,--no-undefined -Wl,--exclude-libs,ALL
    -Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/src/exports.map)
endif()

configure_file(XR_APILAYER_EYETRACKVR_eye_gaze.json.in ${ETVR_LAYER_DIR}/${ETVR_LAYER_NAME}.json @ONLY)

option(ETVR_LAYER_TESTS "Build the fake OpenXR runtime and gaze probe used to test the layer" OFF)
if(ETVR_LAYER_TESTS)
  add_subdirectory(tests)
endif()
