# How to Setup Dev Environment

This project uses NodeJS (v18+) and Yarn. You must install them before continuing.

Next, install the dependencies, navigate to the project directory (`GUI/ETVR`) and run:

```bash
yarn install
```

Then, run the development server:

```bash
yarn tauri dev
```

Finally, the project will open as an app on your device. You can also run the project in the browser by running:

```bash
yarn dev
```

To see a list of all available commands, navigate to the `package.json` file and look at the `scripts` section.

> **Note**: Please use the `yarn format` command before committing any changes to the project. Please fix any errors that are reported by the linter.

## How to Build

To build the project, run:

```bash
yarn tauri build
```

This will create a folder called `target` in the `src-tauri` directory. Inside this folder, you will find the executable for your operating system, as well as an MSI installer for Windows.

## Rust dev environment

If you want to work on the Rust code, you will need to install the Rust toolchain. Starting with RustC.

Then in `vscode` you will need to install the extensions [`rust-analyzer`](https://rust-analyzer.github.io/manual.html#vs-code) and `rustfmt` (rust fmt is optional).

For the `rust-analyzer` extension to work, you will need to add the following to your `.vscode/settings.json` file:

```json
"rust-analyzer.cargo.loadOutDirsFromCheck": true,
"rust-analyzer.checkOnSave.enable": true,
"rust-analyzer.checkOnSave.extraArgs": ["--all-targets"],
"rust-analyzer.checkOnSave.command": "clippy",
"rust-analyzer.checkOnSave.allTargets": true,
"rust-analyzer.files.excludeDirs": ["**/target", "**/node_modules", "**/dist", "**/build", "**/public", "**/assets", "**/src-tauri/target", "**/scripts", "**/src/components", "**/src/interfaces", "**/src/pages", "**/src/static", "**/src/styles", "**/src/utils", ],
"rust-analyzer.files.watcher": "client",
// set the vscode workspace folder as the src-tauri folder
"rust-analyzer.linkedProjects": ["src-tauri"],
```

## Useful Links

- [Tauri](https://tauri.app/)
- [Tauri Docs](https://tauri.app/v1/guides/)
- [TailWindCSS](https://tailwindcss.com/docs/)
- [TailWindCSS PreProcessor](https://tailwindcss.com/docs/using-with-preprocessors)
- [TailWindCSS Forms](https://github.com/tailwindlabs/tailwindcss-forms#readme)
