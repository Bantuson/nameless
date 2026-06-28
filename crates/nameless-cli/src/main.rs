//! `nameless` binary entrypoint.
//!
//! Thin: parse args, dispatch, and map any [`CliError`] to a one-line stderr message + non-zero
//! exit code. All real work lives in [`nameless_cli::cli::run`]. The command logic now lives in the
//! crate's library (`src/lib.rs`) so the Phase-10 HTTP server (`nameless-api`) can reuse the exact
//! same use-cases; this binary is one consumer of that library, the axum server is another.

use clap::Parser;

use nameless_cli::cli::{self, Cli};
use nameless_cli::error::CliError;

fn main() {
    let cli = Cli::parse();
    if let Err(e) = run(cli) {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

fn run(cli: Cli) -> Result<(), CliError> {
    cli::run(cli)
}
