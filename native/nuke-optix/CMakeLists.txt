cmake_minimum_required(VERSION 3.24)

project(HOptixDenoise LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(HDU_VERSION "2.0.1" CACHE STRING "h_denoise_utils version embedded in the node")
set(NUKE_VERSION "17.0v3" CACHE STRING "Nuke version used to locate the NDK")
set(NUKE_ROOT "" CACHE PATH "Nuke installation root")
set(OPTIX_ROOT "" CACHE PATH "OptiX SDK or optix-dev checkout root")
set(CUDA_REDIST_ROOT "" CACHE PATH "Minimal CUDA redistributable root containing cuda.h and cuda.lib")
set(OIDN_ROOT "" CACHE PATH "Intel Open Image Denoise package root")
set(HDU_NUKE_PACKAGE_DIR "HDenoiseNodes")
option(HDU_NUKE_STUB_OPTIX "Build a compile-check plugin without CUDA or OptiX" OFF)
if(WIN32)
    set(HDU_NUKE_BUILD_OIDN_DEFAULT ON)
else()
    set(HDU_NUKE_BUILD_OIDN_DEFAULT OFF)
endif()
option(
    HDU_NUKE_BUILD_OIDN
    "Build the Windows HOidnDenoise node"
    ${HDU_NUKE_BUILD_OIDN_DEFAULT})
if(HDU_NUKE_BUILD_OIDN AND NOT WIN32)
    message(FATAL_ERROR "HOidnDenoise is currently supported on Windows only")
endif()

if(NOT NUKE_ROOT)
    if(WIN32)
        set(NUKE_ROOT "C:/Program Files/Nuke${NUKE_VERSION}")
    else()
        set(NUKE_ROOT "/usr/local/Nuke${NUKE_VERSION}")
    endif()
endif()

set(NUKE_INCLUDE_DIR "${NUKE_ROOT}/include")
if(NOT EXISTS "${NUKE_INCLUDE_DIR}/DDImage/PlanarIop.h")
    message(FATAL_ERROR "Nuke NDK headers were not found under ${NUKE_INCLUDE_DIR}")
endif()

if(WIN32)
    set(NUKE_DDIMAGE_LIBRARY "${NUKE_ROOT}/DDImage.lib")
else()
    find_library(
        NUKE_DDIMAGE_LIBRARY
        NAMES DDImage
        PATHS "${NUKE_ROOT}"
        NO_DEFAULT_PATH
        REQUIRED)
endif()
if(NOT EXISTS "${NUKE_DDIMAGE_LIBRARY}")
    message(FATAL_ERROR "Nuke DDImage library was not found: ${NUKE_DDIMAGE_LIBRARY}")
endif()

set(HDU_OPTIX_INCLUDE_DIR "${CMAKE_CURRENT_LIST_DIR}/../optix-denoiser/include")

if(HDU_NUKE_STUB_OPTIX)
    add_library(
        hdu_optix_core
        STATIC
        "${CMAKE_CURRENT_LIST_DIR}/stub/optix_denoiser_stub.cpp")
else()
    if(CUDA_REDIST_ROOT)
        set(CUDA_INCLUDE_DIR "${CUDA_REDIST_ROOT}/include")
        set(CUDA_DRIVER_LIBRARY "${CUDA_REDIST_ROOT}/lib/x64/cuda.lib")
        if(NOT EXISTS "${CUDA_INCLUDE_DIR}/cuda.h")
            message(FATAL_ERROR "CUDA driver headers were not found under ${CUDA_INCLUDE_DIR}")
        endif()
        if(NOT EXISTS "${CUDA_DRIVER_LIBRARY}")
            message(FATAL_ERROR "CUDA driver import library was not found: ${CUDA_DRIVER_LIBRARY}")
        endif()
    else()
        find_package(CUDAToolkit 12 REQUIRED)
        set(CUDA_INCLUDE_DIR "${CUDAToolkit_INCLUDE_DIRS}")
        set(CUDA_DRIVER_LIBRARY CUDA::cuda_driver)
    endif()

    if(NOT OPTIX_ROOT)
        set(OPTIX_ROOT "${CMAKE_CURRENT_LIST_DIR}/../optix-denoiser/contrib/optix")
    endif()
    if(NOT EXISTS "${OPTIX_ROOT}/include/optix.h")
        message(FATAL_ERROR
            "OptiX headers were not found under ${OPTIX_ROOT}/include. "
            "Run the build script without -SkipOptixFetch or set OPTIX_ROOT.")
    endif()

    add_library(
        hdu_optix_core
        STATIC
        "${CMAKE_CURRENT_LIST_DIR}/../optix-denoiser/src/optix_denoiser.cpp")
    target_include_directories(
        hdu_optix_core
        PRIVATE
        "${OPTIX_ROOT}/include"
        "${CUDA_INCLUDE_DIR}")
    target_link_libraries(
        hdu_optix_core
        PRIVATE
        "${CUDA_DRIVER_LIBRARY}")
endif()

target_include_directories(
    hdu_optix_core
    PUBLIC
    "${HDU_OPTIX_INCLUDE_DIR}")
target_compile_features(hdu_optix_core PUBLIC cxx_std_20)

add_library(HOptixDenoise SHARED "src/HOptixDenoise.cpp")
target_include_directories(
    HOptixDenoise
    SYSTEM PRIVATE
    "${NUKE_INCLUDE_DIR}")
target_compile_definitions(
    HOptixDenoise
    PRIVATE
    HDU_VERSION="${HDU_VERSION}"
    NOMINMAX
    _USE_MATH_DEFINES)
target_link_libraries(
    HOptixDenoise
    PRIVATE
    hdu_optix_core
    "${NUKE_DDIMAGE_LIBRARY}")

if(HDU_NUKE_BUILD_OIDN)
    if(NOT OIDN_ROOT)
        message(FATAL_ERROR "OIDN_ROOT is required when HDU_NUKE_BUILD_OIDN is enabled")
    endif()
    if(NOT EXISTS "${OIDN_ROOT}/include/OpenImageDenoise/oidn.hpp")
        message(FATAL_ERROR "OIDN headers were not found under ${OIDN_ROOT}/include")
    endif()
    if(WIN32)
        set(OIDN_LIBRARY "${OIDN_ROOT}/lib/OpenImageDenoise.lib")
    else()
        find_library(
            OIDN_LIBRARY
            NAMES OpenImageDenoise
            PATHS "${OIDN_ROOT}/lib"
            NO_DEFAULT_PATH
            REQUIRED)
    endif()
    if(NOT EXISTS "${OIDN_LIBRARY}")
        message(FATAL_ERROR "OIDN library was not found: ${OIDN_LIBRARY}")
    endif()

    add_library(HOidnDenoise SHARED "src/HOidnDenoise.cpp")
    target_include_directories(
        HOidnDenoise
        SYSTEM PRIVATE
        "${NUKE_INCLUDE_DIR}")
    target_compile_definitions(
        HOidnDenoise
        PRIVATE
        HDU_VERSION="${HDU_VERSION}"
        NOMINMAX
        _USE_MATH_DEFINES)
    target_link_libraries(
        HOidnDenoise
        PRIVATE
        "${NUKE_DDIMAGE_LIBRARY}")

    add_executable(HOidnBridge "src/HOidnBridge.cpp")
    target_include_directories(
        HOidnBridge
        SYSTEM PRIVATE
        "${OIDN_ROOT}/include")
    target_compile_definitions(HOidnBridge PRIVATE NOMINMAX)
    target_link_libraries(HOidnBridge PRIVATE "${OIDN_LIBRARY}")
    if(MSVC)
        target_link_libraries(HOidnBridge PRIVATE delayimp)
        target_link_options(HOidnBridge PRIVATE /DELAYLOAD:OpenImageDenoise.dll)
    endif()
endif()

if(MSVC)
    set_property(
        TARGET hdu_optix_core HOptixDenoise
        PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
    target_compile_options(HOptixDenoise PRIVATE /W4 /permissive- /EHsc /wd4996)
    target_compile_options(hdu_optix_core PRIVATE /W4 /permissive- /EHsc)
    if(HDU_NUKE_BUILD_OIDN)
        set_property(
            TARGET HOidnDenoise
            PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
        set_property(
            TARGET HOidnBridge
            PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
        target_compile_options(HOidnDenoise PRIVATE /W4 /permissive- /EHsc /wd4996)
        target_compile_options(HOidnBridge PRIVATE /W4 /permissive- /EHsc)
    endif()
else()
    target_compile_options(HOptixDenoise PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(hdu_optix_core PRIVATE -Wall -Wextra -Wpedantic)
    if(HDU_NUKE_BUILD_OIDN)
        target_compile_options(HOidnDenoise PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(HOidnBridge PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()

set_target_properties(
    HOptixDenoise
    PROPERTIES
    PREFIX ""
    OUTPUT_NAME "HOptixDenoise")
if(HDU_NUKE_BUILD_OIDN)
    set_target_properties(
        HOidnDenoise
        PROPERTIES
        PREFIX ""
        OUTPUT_NAME "HOidnDenoise")
endif()

if(APPLE)
    message(FATAL_ERROR "OptiX denoising is not supported on macOS")
elseif(UNIX)
    set_target_properties(HOptixDenoise PROPERTIES SUFFIX ".so" INSTALL_RPATH "$ORIGIN")
    if(HDU_NUKE_BUILD_OIDN)
        set_target_properties(HOidnDenoise PROPERTIES SUFFIX ".so" INSTALL_RPATH "$ORIGIN")
    endif()
endif()

install(
    TARGETS HOptixDenoise
    RUNTIME DESTINATION "${HDU_NUKE_PACKAGE_DIR}"
    LIBRARY DESTINATION "${HDU_NUKE_PACKAGE_DIR}")
if(HDU_NUKE_BUILD_OIDN)
    install(
        TARGETS HOidnDenoise HOidnBridge
        RUNTIME DESTINATION "${HDU_NUKE_PACKAGE_DIR}"
        LIBRARY DESTINATION "${HDU_NUKE_PACKAGE_DIR}")
endif()
install(
    FILES
    "package/init.py"
    "package/menu.py"
    "package/README.md"
    "${CMAKE_CURRENT_LIST_DIR}/../../LICENSE"
    DESTINATION "${HDU_NUKE_PACKAGE_DIR}")

message(STATUS "Nuke root: ${NUKE_ROOT}")
message(STATUS "Nuke version: ${NUKE_VERSION}")
message(STATUS "OptiX stub build: ${HDU_NUKE_STUB_OPTIX}")
message(STATUS "Package directory: ${HDU_NUKE_PACKAGE_DIR}")
message(STATUS "OIDN node build: ${HDU_NUKE_BUILD_OIDN}")
if(HDU_NUKE_BUILD_OIDN)
    message(STATUS "OIDN root: ${OIDN_ROOT}")
endif()
if(NOT HDU_NUKE_STUB_OPTIX)
    message(STATUS "OptiX root: ${OPTIX_ROOT}")
    message(STATUS "CUDA redistributable root: ${CUDA_REDIST_ROOT}")
endif()
