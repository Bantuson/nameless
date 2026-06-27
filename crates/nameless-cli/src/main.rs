//! `nameless` binary entrypoint.
//!
//! Thin: parse args, dispatch, and map any [`CliError`] to a one-line stderr message + non-zero
//! exit code. All real work lives in [`cli::run`].

mod cli;
mod error;
mod output;
mod profile;

use clap::Parser;

use crate::cli::Cli;

fn main() {
    let cli = Cli::parse();
    if let Err(e) = cli::run(cli) {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
