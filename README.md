# ClueBot NG continuous trainer

This repo trains the ANN on a schedule and compares the resulting database with the current production database.

The intention is for it to serve as a step towards being able to safely re-train the database in the future.

## Example Usage

1. Download the reviewed edits
    1. `cbng-trainer download-edits --output=edits.xml`
2. Train a new database
    1. `mkdir -p new/`
    1. `cbng-trainer build-database --input=edits.xml --output new/`
3. Compare the 2 databases
    1. `cbng-trainer compare-database --target new/ --export results/`

## Requirements

1. Python 3.9+
2. Docker on execution host
