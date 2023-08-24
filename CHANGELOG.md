# 📦 Changelog 
[![conventional commits](https://img.shields.io/badge/conventional%20commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![semantic versioning](https://img.shields.io/badge/semantic%20versioning-2.0.0-green.svg)](https://semver.org)
> All notable changes to this project will be documented in this file

## 1.0.0-HSF-and-new-algos-feature-branch.1 (2023-08-24)


### ⚠ BREAKING CHANGES

* CHANGES

### 🍕 Features

* add colorama instead of using escape codes ([1d9dfea](https://github.com/EyeTrackVR/EyeTrackVR/commit/1d9dfeae19cd3ab8fd8252cb466b47576428c1e5))
* add dev container ([a5e36ad](https://github.com/EyeTrackVR/EyeTrackVR/commit/a5e36ad4c468f25901ff473555e51ff1495d9521))
* add taskipy to run tasks via poetry ([2f1d3d9](https://github.com/EyeTrackVR/EyeTrackVR/commit/2f1d3d9275310db87e4bda041c072dd9572eb07e))
* add v2 serial comms with packet headers ([c2aad0e](https://github.com/EyeTrackVR/EyeTrackVR/commit/c2aad0e8590a5533f250c9d87d45e42828930611))
* more readable logging with colorama ([2efa3c3](https://github.com/EyeTrackVR/EyeTrackVR/commit/2efa3c35896d1b10e037afa8c12fc9b780c977be))
* show bitrate, fps, latency in tracking mode ([6163744](https://github.com/EyeTrackVR/EyeTrackVR/commit/61637442c61a8c82e2b38c491d3a409080ccf2a9))
* slightly reduce dropped frame count ([3b5582d](https://github.com/EyeTrackVR/EyeTrackVR/commit/3b5582de6eab3b3e65eb7d76c631cd089a06ee40))
* updated poetry.lock ([632ec2a](https://github.com/EyeTrackVR/EyeTrackVR/commit/632ec2a8384db57e7a70099d26accbe3f97db774))


### 🐛 Bug Fixes

* bring the existing impl to a usable state ([b3f444e](https://github.com/EyeTrackVR/EyeTrackVR/commit/b3f444ee3a066b0cd84e7c9f61c04aa7542fb0ef))
* ensure serial is closed when thread crashed ([4def965](https://github.com/EyeTrackVR/EyeTrackVR/commit/4def96575969e3f22a4a915c9e5e71576403c2c8))
* identify and mitigate latency issues ([295f104](https://github.com/EyeTrackVR/EyeTrackVR/commit/295f10476d2c4ecbe266fbb1544091e58f16e563))
* module leap not found ([a29db80](https://github.com/EyeTrackVR/EyeTrackVR/commit/a29db809099a5122430fba58bb8f5e2f288bd7fb))
* Only ever return one blob when blob tracking ([5a451b4](https://github.com/EyeTrackVR/EyeTrackVR/commit/5a451b4aa5b18dee1a1ce961fec04d653e2a77dd)), closes [#20](https://github.com/EyeTrackVR/EyeTrackVR/issues/20)
* Output all info to OSC unless we're failing to find any data ([764baa5](https://github.com/EyeTrackVR/EyeTrackVR/commit/764baa539dafa0382d95e53730e452cfc48710ec)), closes [#21](https://github.com/EyeTrackVR/EyeTrackVR/issues/21)
* pinv for pseudo inverse when singular matrix ([ca56222](https://github.com/EyeTrackVR/EyeTrackVR/commit/ca5622244528e60ad40e2cc994a80b39afe4bff0))
* pyserial is the correct dep, not serial ([09a9fbb](https://github.com/EyeTrackVR/EyeTrackVR/commit/09a9fbb052483cb96c7283cdbcc44bc57a8e078e))
* rate limit error ([129e07b](https://github.com/EyeTrackVR/EyeTrackVR/commit/129e07bc1c63e632c4c41b2a3d6ae7d6d858ccaf))
* standalone exe ([35e71a2](https://github.com/EyeTrackVR/EyeTrackVR/commit/35e71a212323ec539283a267079e032cb6891c34))
* Update graph background color on events ([5580d48](https://github.com/EyeTrackVR/EyeTrackVR/commit/5580d482f935c36a157053b1ad2a1d7234e6160b)), closes [#24](https://github.com/EyeTrackVR/EyeTrackVR/issues/24)
* when address is set but no devices connected ([6d7630c](https://github.com/EyeTrackVR/EyeTrackVR/commit/6d7630cf6029e2de78aa41bdd468ed4d59898951))


### 🧑‍💻 Code Refactoring

* cleanup imports ([446a20c](https://github.com/EyeTrackVR/EyeTrackVR/commit/446a20cea822189f1f5adf3d10b9d9e252b5186e))
* extract EyeInfo enums and dataclasses ([d6d1938](https://github.com/EyeTrackVR/EyeTrackVR/commit/d6d19383bd0dba3e8af39d2101658eb2dbbaf847))


### 🤖 Build System

* setup pre-release build pipeline ([aa5e6b8](https://github.com/EyeTrackVR/EyeTrackVR/commit/aa5e6b8b34dd13357ed3b4bd7989c0e6b6b29991))
* setup pre-release build pipeline ([a8b73bf](https://github.com/EyeTrackVR/EyeTrackVR/commit/a8b73bf2240aac6b7900ec409fa993bd2a692299))
* setup pre-release build pipeline ([9b27720](https://github.com/EyeTrackVR/EyeTrackVR/commit/9b27720bf9385ca7331895ae625c0b28e380c8b2))
* setup pre-release build pipeline ([e250e4e](https://github.com/EyeTrackVR/EyeTrackVR/commit/e250e4e3539dcf83cdc7ddee24a07b0303ee843e))

## [1.0.0-HSF-and-new-algos-feature-branch.2](https://github.com/EyeTrackVR/EyeTrackVR/compare/v1.0.0-HSF-and-new-algos-feature-branch.1...v1.0.0-HSF-and-new-algos-feature-branch.2) (2023-08-24)


### 🐛 Bug Fixes

* rate limit error ([129e07b](https://github.com/EyeTrackVR/EyeTrackVR/commit/129e07bc1c63e632c4c41b2a3d6ae7d6d858ccaf))

## 1.0.0-HSF-and-new-algos-feature-branch.1 (2023-08-24)


### ⚠ BREAKING CHANGES

* CHANGES

### 🍕 Features

* add colorama instead of using escape codes ([1d9dfea](https://github.com/EyeTrackVR/EyeTrackVR/commit/1d9dfeae19cd3ab8fd8252cb466b47576428c1e5))
* add dev container ([a5e36ad](https://github.com/EyeTrackVR/EyeTrackVR/commit/a5e36ad4c468f25901ff473555e51ff1495d9521))
* add taskipy to run tasks via poetry ([2f1d3d9](https://github.com/EyeTrackVR/EyeTrackVR/commit/2f1d3d9275310db87e4bda041c072dd9572eb07e))
* add v2 serial comms with packet headers ([c2aad0e](https://github.com/EyeTrackVR/EyeTrackVR/commit/c2aad0e8590a5533f250c9d87d45e42828930611))
* more readable logging with colorama ([2efa3c3](https://github.com/EyeTrackVR/EyeTrackVR/commit/2efa3c35896d1b10e037afa8c12fc9b780c977be))
* show bitrate, fps, latency in tracking mode ([6163744](https://github.com/EyeTrackVR/EyeTrackVR/commit/61637442c61a8c82e2b38c491d3a409080ccf2a9))
* slightly reduce dropped frame count ([3b5582d](https://github.com/EyeTrackVR/EyeTrackVR/commit/3b5582de6eab3b3e65eb7d76c631cd089a06ee40))
* updated poetry.lock ([632ec2a](https://github.com/EyeTrackVR/EyeTrackVR/commit/632ec2a8384db57e7a70099d26accbe3f97db774))


### 🐛 Bug Fixes

* bring the existing impl to a usable state ([b3f444e](https://github.com/EyeTrackVR/EyeTrackVR/commit/b3f444ee3a066b0cd84e7c9f61c04aa7542fb0ef))
* ensure serial is closed when thread crashed ([4def965](https://github.com/EyeTrackVR/EyeTrackVR/commit/4def96575969e3f22a4a915c9e5e71576403c2c8))
* identify and mitigate latency issues ([295f104](https://github.com/EyeTrackVR/EyeTrackVR/commit/295f10476d2c4ecbe266fbb1544091e58f16e563))
* Only ever return one blob when blob tracking ([5a451b4](https://github.com/EyeTrackVR/EyeTrackVR/commit/5a451b4aa5b18dee1a1ce961fec04d653e2a77dd)), closes [#20](https://github.com/EyeTrackVR/EyeTrackVR/issues/20)
* Output all info to OSC unless we're failing to find any data ([764baa5](https://github.com/EyeTrackVR/EyeTrackVR/commit/764baa539dafa0382d95e53730e452cfc48710ec)), closes [#21](https://github.com/EyeTrackVR/EyeTrackVR/issues/21)
* pinv for pseudo inverse when singular matrix ([ca56222](https://github.com/EyeTrackVR/EyeTrackVR/commit/ca5622244528e60ad40e2cc994a80b39afe4bff0))
* pyserial is the correct dep, not serial ([09a9fbb](https://github.com/EyeTrackVR/EyeTrackVR/commit/09a9fbb052483cb96c7283cdbcc44bc57a8e078e))
* standalone exe ([35e71a2](https://github.com/EyeTrackVR/EyeTrackVR/commit/35e71a212323ec539283a267079e032cb6891c34))
* Update graph background color on events ([5580d48](https://github.com/EyeTrackVR/EyeTrackVR/commit/5580d482f935c36a157053b1ad2a1d7234e6160b)), closes [#24](https://github.com/EyeTrackVR/EyeTrackVR/issues/24)
* when address is set but no devices connected ([6d7630c](https://github.com/EyeTrackVR/EyeTrackVR/commit/6d7630cf6029e2de78aa41bdd468ed4d59898951))


### 🧑‍💻 Code Refactoring

* cleanup imports ([446a20c](https://github.com/EyeTrackVR/EyeTrackVR/commit/446a20cea822189f1f5adf3d10b9d9e252b5186e))
* extract EyeInfo enums and dataclasses ([d6d1938](https://github.com/EyeTrackVR/EyeTrackVR/commit/d6d19383bd0dba3e8af39d2101658eb2dbbaf847))


### 🤖 Build System

* setup pre-release build pipeline ([aa5e6b8](https://github.com/EyeTrackVR/EyeTrackVR/commit/aa5e6b8b34dd13357ed3b4bd7989c0e6b6b29991))
* setup pre-release build pipeline ([a8b73bf](https://github.com/EyeTrackVR/EyeTrackVR/commit/a8b73bf2240aac6b7900ec409fa993bd2a692299))
* setup pre-release build pipeline ([9b27720](https://github.com/EyeTrackVR/EyeTrackVR/commit/9b27720bf9385ca7331895ae625c0b28e380c8b2))
* setup pre-release build pipeline ([e250e4e](https://github.com/EyeTrackVR/EyeTrackVR/commit/e250e4e3539dcf83cdc7ddee24a07b0303ee843e))

## 1.0.0-HSF-and-new-algos-feature-branch.1 (2023-08-24)


### 🍕 Features

* add colorama instead of using escape codes ([1d9dfea](https://github.com/EyeTrackVR/EyeTrackVR/commit/1d9dfeae19cd3ab8fd8252cb466b47576428c1e5))
* add dev container ([a5e36ad](https://github.com/EyeTrackVR/EyeTrackVR/commit/a5e36ad4c468f25901ff473555e51ff1495d9521))
* add taskipy to run tasks via poetry ([2f1d3d9](https://github.com/EyeTrackVR/EyeTrackVR/commit/2f1d3d9275310db87e4bda041c072dd9572eb07e))
* add v2 serial comms with packet headers ([c2aad0e](https://github.com/EyeTrackVR/EyeTrackVR/commit/c2aad0e8590a5533f250c9d87d45e42828930611))
* more readable logging with colorama ([2efa3c3](https://github.com/EyeTrackVR/EyeTrackVR/commit/2efa3c35896d1b10e037afa8c12fc9b780c977be))
* show bitrate, fps, latency in tracking mode ([6163744](https://github.com/EyeTrackVR/EyeTrackVR/commit/61637442c61a8c82e2b38c491d3a409080ccf2a9))
* slightly reduce dropped frame count ([3b5582d](https://github.com/EyeTrackVR/EyeTrackVR/commit/3b5582de6eab3b3e65eb7d76c631cd089a06ee40))
* updated poetry.lock ([632ec2a](https://github.com/EyeTrackVR/EyeTrackVR/commit/632ec2a8384db57e7a70099d26accbe3f97db774))


### 🐛 Bug Fixes

* bring the existing impl to a usable state ([b3f444e](https://github.com/EyeTrackVR/EyeTrackVR/commit/b3f444ee3a066b0cd84e7c9f61c04aa7542fb0ef))
* ensure serial is closed when thread crashed ([4def965](https://github.com/EyeTrackVR/EyeTrackVR/commit/4def96575969e3f22a4a915c9e5e71576403c2c8))
* identify and mitigate latency issues ([295f104](https://github.com/EyeTrackVR/EyeTrackVR/commit/295f10476d2c4ecbe266fbb1544091e58f16e563))
* Only ever return one blob when blob tracking ([5a451b4](https://github.com/EyeTrackVR/EyeTrackVR/commit/5a451b4aa5b18dee1a1ce961fec04d653e2a77dd)), closes [#20](https://github.com/EyeTrackVR/EyeTrackVR/issues/20)
* Output all info to OSC unless we're failing to find any data ([764baa5](https://github.com/EyeTrackVR/EyeTrackVR/commit/764baa539dafa0382d95e53730e452cfc48710ec)), closes [#21](https://github.com/EyeTrackVR/EyeTrackVR/issues/21)
* pinv for pseudo inverse when singular matrix ([ca56222](https://github.com/EyeTrackVR/EyeTrackVR/commit/ca5622244528e60ad40e2cc994a80b39afe4bff0))
* pyserial is the correct dep, not serial ([09a9fbb](https://github.com/EyeTrackVR/EyeTrackVR/commit/09a9fbb052483cb96c7283cdbcc44bc57a8e078e))
* Update graph background color on events ([5580d48](https://github.com/EyeTrackVR/EyeTrackVR/commit/5580d482f935c36a157053b1ad2a1d7234e6160b)), closes [#24](https://github.com/EyeTrackVR/EyeTrackVR/issues/24)
* when address is set but no devices connected ([6d7630c](https://github.com/EyeTrackVR/EyeTrackVR/commit/6d7630cf6029e2de78aa41bdd468ed4d59898951))


### 🧑‍💻 Code Refactoring

* cleanup imports ([446a20c](https://github.com/EyeTrackVR/EyeTrackVR/commit/446a20cea822189f1f5adf3d10b9d9e252b5186e))
* extract EyeInfo enums and dataclasses ([d6d1938](https://github.com/EyeTrackVR/EyeTrackVR/commit/d6d19383bd0dba3e8af39d2101658eb2dbbaf847))


### 🤖 Build System

* setup pre-release build pipeline ([aa5e6b8](https://github.com/EyeTrackVR/EyeTrackVR/commit/aa5e6b8b34dd13357ed3b4bd7989c0e6b6b29991))
* setup pre-release build pipeline ([a8b73bf](https://github.com/EyeTrackVR/EyeTrackVR/commit/a8b73bf2240aac6b7900ec409fa993bd2a692299))
* setup pre-release build pipeline ([9b27720](https://github.com/EyeTrackVR/EyeTrackVR/commit/9b27720bf9385ca7331895ae625c0b28e380c8b2))
* setup pre-release build pipeline ([e250e4e](https://github.com/EyeTrackVR/EyeTrackVR/commit/e250e4e3539dcf83cdc7ddee24a07b0303ee843e))
