add_library(usermod_repeater INTERFACE)

target_sources(usermod_repeater INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/repeater.c
    ${CMAKE_CURRENT_LIST_DIR}/tiny_mdns.c
)

target_include_directories(usermod_repeater INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_repeater)
