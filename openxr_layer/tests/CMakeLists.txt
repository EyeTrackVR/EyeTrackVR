# Test tools: a strict fake OpenXR runtime and a headless gaze probe app.
#   gaze_probe 50 --direct <layer lib> <fake_runtime lib>      no loader needed
#   gaze_probe 50                                               through the system loader, e.g. with
#     XR_RUNTIME_JSON=<build>/tests/fake_runtime.json (or Monado)
#     XR_API_LAYER_PATH=<build>/eyetrackvr_openxr_layer XR_ENABLE_API_LAYERS=XR_APILAYER_EYETRACKVR_eye_gaze

foreach(t fake_runtime gaze_probe)
  if(t STREQUAL fake_runtime)
    add_library(${t} SHARED fake_runtime.cpp)
    set_target_properties(${t} PROPERTIES PREFIX "" CXX_VISIBILITY_PRESET hidden)
  else()
    add_executable(${t} gaze_probe.cpp)
    if(NOT WIN32)
      target_link_libraries(${t} PRIVATE ${CMAKE_DL_LIBS})
    endif()
  endif()
  target_include_directories(${t} SYSTEM PRIVATE ../third_party/openxr)
  target_compile_definitions(${t} PRIVATE XR_NO_PROTOTYPES _CRT_SECURE_NO_WARNINGS)
  set_target_properties(${t} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_CURRENT_BINARY_DIR}
    LIBRARY_OUTPUT_DIRECTORY_RELEASE ${CMAKE_CURRENT_BINARY_DIR})
endforeach()

# Optional Vulkan session in the probe (ETVR_PROBE_VULKAN=1) for runtimes that don't focus headless sessions.
find_package(Vulkan QUIET)
if(Vulkan_FOUND AND NOT WIN32)
  target_compile_definitions(gaze_probe PRIVATE ETVR_PROBE_VULKAN)
  target_link_libraries(gaze_probe PRIVATE Vulkan::Vulkan)
endif()

file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/fake_runtime.json
  "{ \"file_format_version\": \"1.0.0\", \"runtime\": { \"name\": \"EyeTrackVR fake runtime\", \"library_path\": \"./fake_runtime${CMAKE_SHARED_LIBRARY_SUFFIX}\" } }\n")
