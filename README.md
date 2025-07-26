# ClueBot NG trainer

This repo trains the bayes / ann databases on given edit group(s).

It is explicitly designed to run on toolforge and utilises both the toolforge jobs api & kubernetes api.

## Commands

### `run-edit-sets`

This is the main entrypoint, run on a schedule.

It builds the relevant `run-edit-set` commands based on the edit groups exposed via the review api.

Example local execution:
```
cbng-trainer run-edit-sets --edit-set 'Report Interface Import' --edit-set 'Sampled Main Namespace Edits' --print-only

INFO:__main__:Using sampled edits as fallback trial group for Report Interface Import
cbng-trainer run-edit-set --kubernetes-namespace="tool-cluebotng-trainer" --target-name="Report Interface Import" --instance-name="2025-08-01 18:36:31" --release-ref="v1.0.3" --trainer-host="https://cluebotng-trainer.toolforge.org" --download-training="https://cluebotng-review.toolforge.org/api/v1/edit-groups/2/dump-editset/" --download-trial="https://cluebotng-review.toolforge.org/api/v1/edit-groups/26/dump-editset/"

cbng-trainer run-edit-set --kubernetes-namespace="tool-cluebotng-trainer" --target-name="Sampled Main Namespace Edits" --instance-name="2025-08-01 18:36:31" --release-ref="v1.0.3" --trainer-host="https://cluebotng-trainer.toolforge.org" --download-training="https://cluebotng-review.toolforge.org/api/v1/edit-groups/26/dump-editset/"
```

For each execution, a `job` is made via the toolforge `jobs` framework.

### `run-edit-set`

This does all the heavy lifting for a specific edit group, executing the `steps` required for training.

Example local execution:
```
cbng-trainer run-edit-set --kubernetes-namespace="tool-cluebotng-trainer" --target-name="Report Interface Import" --instance-name="2025-08-01 19:44:00" --release-ref="v1.0.3" --trainer-host="https://cluebotng-trainer.toolforge.org" --download-training="https://cluebotng-review.toolforge.org/api/v1/edit-groups/2/dump-editset/" --download-trial="https://cluebotng-review.toolforge.org/api/v1/edit-groups/26/dump-editset/"

INFO:__main__:Downloading files
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-download in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Downloading https://cluebotng-review.toolforge.org/api/v1/edit-groups/2/dump-editset/ to /tmp/465b4882a11d45ab94c88451bb5fa6ed
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/465b4882a11d45ab94c88451bb5fa6ed to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/edit-sets/train.xml
INFO:cbng_trainer.common.steps:Downloading https://cluebotng-review.toolforge.org/api/v1/edit-groups/26/dump-editset/ to /tmp/58cb783b9016405ea2a181f11573456a
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/58cb783b9016405ea2a181f11573456a to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/edit-sets/trial.xml
INFO:__main__:Running bayes train
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-bayes-train in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Finished bayes_train: Processed 397 edits.
 / 
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/main_bayes_train.dat to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/main_bayes_train.dat
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/two_bayes_train.dat to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/two_bayes_train.dat
INFO:__main__:Creating main bayes database
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-main-bayes-db in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Finished create_bayes_db (bayes): Processing words ...
208
Pruning ...
 / 
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/bayes.db to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/bayes.db
INFO:__main__:Creating two bayes database
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-two-bayes-db in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Finished create_bayes_db (two_bayes): Processing words ...
366
Pruning ...
 / 
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/two_bayes.db to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/two_bayes.db
INFO:__main__:Running ann train
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-ann-train in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Finished ann_train: Processed 397 edits.
 / 
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/main_ann_train.dat to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/main_ann_train.dat
INFO:__main__:Running ann create
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-ann-create in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:Finished create_ann: Inputs: 161  Outputs: 1
Max epochs      150. Desired error: 0.0370000005.
Epochs            1. Current error: 0.2050748765. Bit fail 397.
Epochs            2. Current error: 0.0000000000. Bit fail 0.
Saving file.
 / 
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/data/main_ann.fann to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/artifacts/main_ann.fann
INFO:__main__:Executing trial
INFO:cbng_trainer.common.kubernetes:Spawning container 6930c-report-interface-import-trial in tool-cluebotng-trainer
INFO:cbng_trainer.common.steps:0inished trial_run: 
Processed 0 edits.

INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/debug.xml to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/debug.xml
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/details.txt to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/details.txt
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/falsenegatives.txt to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/falsenegatives.txt
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/falsepositives.txt to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/falsepositives.txt
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/report.txt to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/report.txt
INFO:cbng_trainer.common.kubernetes:Uploading /tmp/cbng-core/trialreport/thresholdtable.txt to https://cluebotng-trainer.toolforge.org/Report%20Interface%20Import/2025-08-01%2019%3A44%3A00/trial/thresholdtable.txt
```

_Note: this requires having access to the kubernetes API from your local environment_

### `run-file-api`

Given our purpose in life is to deal with files, we need to access disk... however we don't really want to run on the NFS nodes as they are regularly oversubscribed.

The web api provides 2 services:

1. Read only access (to `public_html`) for humans and tooling
2. Write access (to `public_html`) for tooling

Essentially at container launch we pull files down from the api and at the end we push files up to the api.

Insert something about a fancy object store here...

## Deployment

We use `build service` and re-build images on commits to `main` (triggered via GitHub actions).

Unfortunately `webservice` type jobs are not supported via that workflow yet, so we have `fab deploy` to deal with that. 
