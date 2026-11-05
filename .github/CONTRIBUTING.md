<!-- <img src="./img/logo.png" alt="Logo" align="right" height="76"/> -->

# Contributing

**Any contribution helps our team and make EyeTrackVR better for the entire community!**

Everybody is welcome and invited to contribute to the EyeTrackVR Project by:

* Testing newly released features and reporting issues.
* Providing Pull Requests (Features, Proof of Concepts, Language files or Fixes)
* Contributing missing documentation for features and devices in our [documentation](https://redhawk989.github.io/EyeTrackVR/)

This document describes rules that are in effect for this repository, meant for handling issues by contributors in the issue tracker and PRs.

## Opening New Issues

**Issue tracker is NOT a general discussion forum!**

1. Opening an issue means that a problem exists in the code and should be addressed by the project contributors.
2. When opening an issue, it is required to fill out the presented template. The requested information is important! If the template is ignored or insufficient info about the issue is provided, the issue may be closed.
3. Questions of type "How do I..." or "Can you please help me with..." or "Can EyeTrackVR do..." WILL NOT be handled here. Such questions should be directed at a discussion forum or to the EyeTrackVR Support Chat. All issues of this type will be closed with a simple reference to this contributing policy.
4. Issues about topics already handled in the documentation will be closed in a similar manner.
5. Issues for unmerged PRs will be closed. If there is an issue with a PR, the explanation should be added to the PR itself.
6. Issues with accompanied investigation that shows the root of the problem should be given priority.
7. Duplicate issues will be closed.

## Triaging of Issues/PR's

1. Any contributor to the project can participate in the triaging process, if he/she chooses to do so.
2. An issue that needs to be closed, either due to not complying with this policy, or for other reasons, should be closed by a contributor.
3. Issues that are accepted should be marked with appropriate labels.
4. Issues that could impact functionality for many users should be considered severe.
5. Issues caused by the SDK or chip should not be marked severe, as there usually isn’t much to be done. Common sense should be applied when deciding. Such issues should be documented in the Wiki, for reference by users.
6. Issues with feature requests should be discussed for viability/desirability.
7. Feature requests or changes that are meant to address a very specific/limited use case, especially if at the expense of increased code complexity, may be denied, or may be required to be redesigned, generalized, or simplified.
8. Feature requests that are not accompanied by a PR:
    * could be closed immediately (denied).
    * could be closed after some predetermined period of time (left as candidate for somebody to pick up).
9. In some cases, feedback may be requested from the issue reporter, either as additional info for clarification, additional testing, or other. If no feedback is provided, the issue may be closed by a contributor or after 30 days by the STALE bot.

## Pull requests

A Pull Request (PR) is the process where code modifications are managed in GitHub.

The process is straight-forward.

* Read [How to get faster PR reviews](https://github.com/kubernetes/community/blob/master/contributors/guide/pull-requests.md#best-practices-for-faster-reviews) by Kubernetes (but skip step 0)
* Fork the EyeTrackVR Repository [git repository](https://github.com/RedHawk989/EyeTrackVR).
* Install [Git LFS](https://git-lfs.com) before cloning: the ONNX models in `eyetrackapp/assets/models` are stored in LFS.
* Write/Change the code in your Fork for a new feature, bug fix, new sensor, optimization, etc.
* Ensure tests work.
* Create a Pull Request against the [**development**](https://github.com/RedHawk989/EyeTrackVR/tree/dev) branch of EyeTrackVR.

1. All pull requests must be done against the development branch.
2. Only relevant files should be touched (Also beware if your editor has auto-formatting feature enabled).
3. Only one feature/fix should be added per PR.
4. If adding a new functionality (new hardware, new library support) not related to an existing component move it to it's own modules (.ino file).
5. PRs that don't compile (fail in CI Tests) or cause coding errors will not be merged. Please fix the issue. Same goes for PRs that are raised against older commit in development - you might need to rebase and resolve conflicts.
6. All pull requests should undergo peer review by at least one contributor other than the creator, excepts for the owner.
7. All pull requests should consider updates to the documentation.
8. Pull requests that address an outstanding issue, particularly an issue deemed to be severe, should be given priority.
9. If a PR is accepted, then it should undergo review and updated based on the feedback provided, then merged.
10. By submitting a PR, it is needed to use the provided PR template and check all boxes, performing the required tasks and accepting the CLA.
11. Pull requests that don't meet the above will be denied and closed.

--------------------------------------

## Contributor License Agreement (CLA)

```txt
By submitting a contribution to this project, I agree that:

1. Origin. I certify that:

   (a) I created the contribution in whole or in part and have the
       right to submit it; or

   (b) the contribution is based on previous work that, to the best
       of my knowledge, is covered by an appropriate open source
       license, and that license lets me submit the work with my
       changes; or

   (c) the contribution was provided directly to me by someone who
       certified (a), (b) or (c), and I have not modified it.

2. Third-party work. If any part of the contribution was not created
   by me, I have identified that part and its license in my pull
   request.

3. License to the Project Owner. "Project Owner" means Prohurtz, the
   owner of the EyeTrackVR project, and any successor or assignee of
   the project. I keep the copyright in my contribution, and I grant
   the Project Owner a perpetual, worldwide, non-exclusive,
   royalty-free, irrevocable, sublicensable and transferable license
   to use, copy, modify, distribute and relicense my contribution, on
   its own or as part of any work, under any license or terms the
   Project Owner chooses, including proprietary or commercial terms.
   For third-party work identified under section 2, this license
   covers only the rights I am able to grant.

4. No further action needed. The Project Owner may use these rights
   at any time without notifying me, consulting me, getting further
   permission from me, or paying me.

5. Public record. This project and my contribution are public. A
   record of the contribution, including any personal information I
   submit with it, is kept indefinitely and may be redistributed.
```

To accept the CLA, tick `I accept the CLA` in the PR template. The box is opt-in, so you have to tick it yourself.

Contributions submitted before this version of the CLA remain under the version in effect when they were submitted.

Sections 1 and 5 are based on the Linux [Developer Certificate of Origin](http://elinux.org/Developer_Certificate_Of_Origin), and this text is available under the [Creative Commons Attribution-ShareAlike 3.0 Unported License](http://creativecommons.org/licenses/by-sa/3.0/). It does not use sign-offs, because GitHub keeps a history of each PR's commits and comments under your username.

**Why a CLA?**

A **license** grants "outbound" rights to the people who use the project. A **CLA** grants "inbound" rights from contributors to the project. This one confirms that you are entitled to submit your work, and it lets the Project Owner keep distributing, changing and relicensing the project without having to find every past contributor.

## Code owners

In addition to @RedHawk989 the following code is mainly owned by:

| Code                       | Owner
|----------------------------|---------------------------
| EyeTrackVR Drivers         |
| all                        | @RedHawk989
|                            |
| EyeTrackVR Source Code     |
| all                        | @RedHawk989
|                            |
| RANSAC and Calibration     |
| all                        | @SummerSigh
|                            |
| Github Pages               | @ZanzyTHEbar
