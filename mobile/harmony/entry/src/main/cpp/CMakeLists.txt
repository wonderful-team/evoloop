cmake_minimum_required(VERSION 3.11)
project(rnapp)

set(RNOH_APP_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(NODE_MODULES "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../node_modules")
set(RNOH_CPP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../../oh_modules/@rnoh/react-native-openharmony/src/main/cpp")
set(RNOH_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")
set(LOG_VERBOSITY_LEVEL 1)
set(CMAKE_ASM_FLAGS "-Wno-error=unused-command-line-argument -Qunused-arguments")
set(CMAKE_CXX_FLAGS "-fstack-protector-strong -Wl,-z,relro,-z,now,-z,noexecstack -s -fPIE -pie -include \"${CMAKE_CURRENT_SOURCE_DIR}/butter_compat.h\"")
set(WITH_HITRACE_SYSTRACE ON)
set(WITH_HITRACE_REACT_MARKER ON)
set(OH_MODULES_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../../oh_modules") # required by 'autolink_libraries'

add_subdirectory("${RNOH_CPP_DIR}" ./rn)

include("${CMAKE_CURRENT_SOURCE_DIR}/autolinking.cmake")

# Manual linking for skipped libraries
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-reanimated/src/main/cpp" ./rn_reanimated)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-permissions/src/main/cpp" ./rn_permissions)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-webview/src/main/cpp" ./rn_webview)
add_subdirectory("${OH_MODULES_DIR}/@react-native-oh-tpl/async-storage/src/main/cpp" ./rn_async_storage)
add_subdirectory("${OH_MODULES_DIR}/@react-native-oh-tpl/react-native-audio-recorder-player/src/main/cpp" ./rn_audio_recorder_player)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-safe-area-context/src/main/cpp" ./rn_safe_area)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-video/src/main/cpp" ./rn_video)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/flash-list/src/main/cpp" ./rn_flash_list)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/clipboard/src/main/cpp" ./rn_clipboard)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-vision-camera/src/main/cpp" ./rn_vision_camera)
add_subdirectory("${OH_MODULES_DIR}/@react-native-oh-tpl/react-native-gesture-handler/src/main/cpp" ./rn_gesture_handler)
add_subdirectory("${OH_MODULES_DIR}/@react-native-ohos/react-native-image-crop-picker/src/main/cpp" ./rn_image_crop_picker)

file(GLOB_RECURSE GENERATED_CPP_FILES "${CMAKE_CURRENT_SOURCE_DIR}/generated/*.cpp") # this line is needed by codegen v1
add_library(rnoh_app SHARED
    ${GENERATED_CPP_FILES}
    "./PackageProvider.cpp"
    "${RNOH_CPP_DIR}/RNOHAppNapiBridge.cpp"
)
target_include_directories(rnoh_app PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}/generated/evo_loop_mobile"
)
target_link_libraries(rnoh_app PUBLIC rnoh)

# Link manual third-party libraries
target_link_libraries(rnoh_app PUBLIC
    rnoh_reanimated
    rnoh_permissions
    rnoh_webview
    rnoh_async_storage
    rnoh_audio_recorder_player
    rnoh_safe_area
    rnoh_video
    rnoh_flash_list
    rnoh_clipboard
    rnoh_vision_camera
    rnoh_gesture_handler
    rnoh_image_crop_picker
)

autolink_libraries(rnoh_app)
