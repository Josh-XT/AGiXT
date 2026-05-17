#
# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

liblc3_src += \
    $(SRC_DIR)/attdet.c \
    $(SRC_DIR)/bits.c \
    $(SRC_DIR)/bwdet.c \
    $(SRC_DIR)/energy.c \
    $(SRC_DIR)/lc3.c \
    $(SRC_DIR)/ltpf.c \
    $(SRC_DIR)/mdct.c \
    $(SRC_DIR)/plc.c \
    $(SRC_DIR)/sns.c \
    $(SRC_DIR)/spec.c \
    $(SRC_DIR)/tables.c \
    $(SRC_DIR)/tns.c

liblc3_cflags += -ffast-math

$(eval $(call add-lib,liblc3))

default: liblc3
