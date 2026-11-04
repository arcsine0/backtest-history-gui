# Build Standalone App

> ref: <https://pytauri.github.io/pytauri/latest/usage/tutorial/build-standalone/>

Run `pnpm tauri build` from `desktop`. On Windows it downloads portable Python if necessary,
installs Stratara into it, then bundles that runtime with the app. Do not run `cargo build` or
`pnpm exec tauri build` directly for a distributable build: those commands omit embedded Python.

Install or launch the generated NSIS/MSI output under `target/bundle-release/bundle`, not the raw
`target/release/stratara.exe` file.
