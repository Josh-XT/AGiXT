#  Copyright © 2022 Intel Corporation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

inc = include_directories('../include')

lc3_sources = [
	'attdet.c',
	'bits.c',
	'bwdet.c',
	'energy.c',
	'lc3.c',
	'ltpf.c',
	'mdct.c',
	'plc.c',
	'sns.c',
	'spec.c',
	'tables.c',
	'tns.c'
]

lc3lib = library('lc3',
		lc3_sources,
		dependencies: m_dep,
		include_directories: inc,
		soversion: 1,
		install: true)

lc3_install_headers = [
	'../include/lc3_private.h',
	'../include/lc3.h',
	'../include/lc3_cpp.h'
]

install_headers(lc3_install_headers)

pkg_mod = import('pkgconfig')

pkg_mod.generate(libraries : lc3lib,
                 name : 'liblc3',
                 filebase : 'lc3',
                 description : 'LC3 codec library')

#Declare dependency
liblc3_dep = declare_dependency(
	link_with : lc3lib,
	include_directories : inc)

if meson.version().version_compare('>= 0.54.0')
	meson.override_dependency('liblc3', liblc3_dep)
endif
