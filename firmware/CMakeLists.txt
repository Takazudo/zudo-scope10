cmake_minimum_required(VERSION 3.13)
if(NOT DEFINED ENV{PICO_SDK_PATH})
  message(FATAL_ERROR "Set PICO_SDK_PATH to your reviewed local Pico SDK checkout.")
endif()
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(zudo_scope10_p0 C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(PICO_BOARD pico CACHE STRING "Pico H shares the Pico pinout")
pico_sdk_init()
add_executable(scope10_diagnostic src/pico_diagnostic.c src/scope_core.c)
target_include_directories(scope10_diagnostic PRIVATE src)
target_compile_options(scope10_diagnostic PRIVATE -Wall -Wextra)
target_link_libraries(scope10_diagnostic pico_stdlib hardware_adc hardware_gpio m)
pico_enable_stdio_usb(scope10_diagnostic 1)
pico_enable_stdio_uart(scope10_diagnostic 0)
pico_add_extra_outputs(scope10_diagnostic)

# 10 kS/s/channel sequential acquisition engine (design only until G05 closes on the bench).
add_executable(scope10_acq src/acq_rp2040.c src/acq_engine.c src/scope_core.c src/lcd_safe_pins.c)
target_include_directories(scope10_acq PRIVATE src)
target_compile_options(scope10_acq PRIVATE -Wall -Wextra)
# ACQ_IN_RAM: the mux-step path must not run from XIP flash. The short USB stdout timeout
# bounds how long a stalled serial host can block the drain loop (overruns are counted).
target_compile_definitions(scope10_acq PRIVATE ACQ_IN_RAM=1 PICO_STDIO_USB_STDOUT_TIMEOUT_US=2000)
target_link_libraries(scope10_acq pico_stdlib pico_multicore hardware_adc hardware_dma hardware_pwm
                      hardware_irq hardware_clocks hardware_gpio m)
pico_enable_stdio_usb(scope10_acq 1)
pico_enable_stdio_uart(scope10_acq 0)
pico_add_extra_outputs(scope10_acq)

# LCD backend + ten-pane renderer (firmware/LCD-BACKEND.md). OFF by default: the module's
# power path (G01) is not physically verified. Configure with -DSCOPE_ENABLE_LCD=1 to build it.
option(SCOPE_ENABLE_LCD "Build scope10_acq with the Waveshare LCD backend and renderer" OFF)
if(SCOPE_ENABLE_LCD)
  target_sources(scope10_acq PRIVATE src/display_waveshare.c src/lcd_bridge.c src/scope_render.c)
  target_compile_definitions(scope10_acq PRIVATE SCOPE_ENABLE_LCD=1)
  target_link_libraries(scope10_acq hardware_spi)
endif()
