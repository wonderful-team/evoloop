// preload-deps.cc
//
// This file is compiled into libsherpa_onnx_native.so.
// It uses a __attribute__((constructor)) function to ensure that
// libonnxruntime.so and libsherpa-onnx-c-api.so are loaded with
// RTLD_GLOBAL *before* the NAPI Init function runs.
//
// On OpenHarmony NEXT, each native module (.so loaded via NAPI) is loaded
// inside its own linker namespace. The RUNPATH "$ORIGIN" does allow the
// dynamic linker to find sibling .so files, but the NAPI namespace only
// resolves dependencies at NAPI load time - which means if a dependency
// can't be loaded (e.g. due to namespace restrictions), dlopen of
// libsherpa_onnx_native.so itself fails, and the module is never initialized.
//
// By calling dlopen with RTLD_NOW | RTLD_GLOBAL inside a constructor, we
// force resolution within the same namespace as libsherpa_onnx_native.so,
// and make the symbols available globally, avoiding duplicate C++ runtimes.

#ifdef __OHOS__
#include <dlfcn.h>
#include <hilog/log.h>
#include <string>

static constexpr char SHERPA_LOG_TAG[] = "SHERPA_PRELOAD";

static void sherpa_preload_library(const char* libname) {
  void* handle = dlopen(libname, RTLD_NOW | RTLD_GLOBAL);
  if (!handle) {
    OH_LOG_Print(LOG_APP, LOG_ERROR, 0xFF00, SHERPA_LOG_TAG,
                 "Failed to preload %{public}s: %{public}s", libname, dlerror());
  } else {
    OH_LOG_Print(LOG_APP, LOG_INFO, 0xFF00, SHERPA_LOG_TAG,
                 "Successfully preloaded %{public}s", libname);
  }
}

__attribute__((constructor))
static void sherpa_onnx_preload_deps(void) {
  OH_LOG_Print(LOG_APP, LOG_INFO, 0xFF00, SHERPA_LOG_TAG,
               "sherpa_onnx_native constructor: preloading dependencies");
  // Load in dependency order: C++ runtime first, then onnxruntime, then C API
  sherpa_preload_library("libc++_shared.so");
  sherpa_preload_library("libonnxruntime.so");
  sherpa_preload_library("libsherpa-onnx-c-api.so");
  OH_LOG_Print(LOG_APP, LOG_INFO, 0xFF00, SHERPA_LOG_TAG,
               "sherpa_onnx_native constructor: done");
}
#endif // __OHOS__
