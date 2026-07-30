cmake_minimum_required(VERSION 3.18)
project(Denoiser LANGUAGES CXX)

include(GNUInstallDirs)

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} ${PROJECT_SOURCE_DIR}/cmake)

set(CUDA_REDIST_ROOT "" CACHE PATH "Minimal CUDA redistributable root")
if(CUDA_REDIST_ROOT)
    if(NOT WIN32)
        message(FATAL_ERROR "CUDA_REDIST_ROOT currently supports Windows packages only")
    endif()
    set(CUDA_INCLUDE_DIRS "${CUDA_REDIST_ROOT}/include")
    set(CUDA_DRIVER_LIBRARY "${CUDA_REDIST_ROOT}/lib/x64/cuda.lib")
    foreach(required_path
            "${CUDA_INCLUDE_DIRS}/cuda.h"
            "${CUDA_DRIVER_LIBRARY}")
        if(NOT EXISTS "${required_path}")
            message(FATAL_ERROR "CUDA redistributable file is missing: ${required_path}")
        endif()
    endforeach()
else()
    find_package(CUDAToolkit 12 REQUIRED)
    set(CUDA_INCLUDE_DIRS ${CUDAToolkit_INCLUDE_DIRS})
    set(CUDA_DRIVER_LIBRARY CUDA::cuda_driver)
endif()

find_package(OpenImageIO CONFIG REQUIRED)
find_package(OpenEXR CONFIG REQUIRED)
find_package(Imath CONFIG REQUIRED)

message(STATUS "Found OpenImageIO: ${OpenImageIO_DIR}"
               " (includes: ${OpenImageIO_INCLUDE_DIRS}, library: ${OpenImageIO_LIBRARIES})")
message(STATUS "CUDA includes: ${CUDA_INCLUDE_DIRS}")
message(STATUS "CUDA driver library: ${CUDA_DRIVER_LIBRARY}")

add_executable(
    ${PROJECT_NAME}
    src/main.cpp
    src/optix_denoiser.cpp)

target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_20)
target_include_directories(${PROJECT_NAME} PRIVATE "include")
target_include_directories(
    ${PROJECT_NAME}
    SYSTEM PRIVATE
    "contrib/optix/include"
    ${CUDA_INCLUDE_DIRS})
target_link_libraries(
    ${PROJECT_NAME}
    PRIVATE
    ${CUDA_DRIVER_LIBRARY}
    openimageio::openimageio
    OpenEXR::OpenEXR
    Imath::Imath)

if(MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE /W4 /permissive- /EHsc)
else()
    target_compile_options(${PROJECT_NAME} PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Install app and Conan OpenImageIO artifacts explicitly.
install(TARGETS ${PROJECT_NAME}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
