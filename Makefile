# Copyright 2015 SICS Swedish ICT AB
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

EMACS = /Applications/Emacs.app/Contents/MacOS/Emacs

MONITOR_FILES = ceilocomm.py confserver.py monconf.py monitor.py run_monitor.py sampler.py utc.py version.py

GENERATED_FILES = 

all: dist

.PHONY: doc

doc: usage.txt
	$(EMACS) --batch --find-file=$< --eval="(setq delete-old-versions t)" --eval="(org-export-as-html 4)"

GENERATED_FILES += usage.html

TIMESTAMP=$(shell date "+%Y-%m-%dT%H_%M_%S")

.PHONY: dist

dist: doc $(MONITOR_FILES)
	tar -czvf monitor_$(TIMESTAMP).tgz $(MONITOR_FILES) usage.html

GENERATED_FILES += monitor.tgz

.PHONY: clean

clean:
	rm -rf dummy $(GENERATED_FILES)
