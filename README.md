# ClueBot NG trainer

This repo trains the bayes / ann databases on given edit group(s).

It is explicitly designed to run on toolforge and utilises both the toolforge jobs api & kubernetes api.

## Commands

### `run-edit-sets`

This is the main entrypoint, run on a schedule.

It builds the relevant `run-edit-set` commands based on the edit groups exposed via the review api.

Example local execution:

```
cbng-trainer run-edit-sets --print-only

INFO:__main__:Using sampled edits as fallback trial group for Report Interface Import
cbng-trainer run-edit-set --image-name="tools-harbor.wmcloud.org/tool-cluebotng-trainer/trainer:latest" --target-name="Legacy Report Interface Import" --instance-name="2025-08-03 22:56:16" --release-ref="v1.0.3" --trainer-host="http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000" --download-training="http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000/api/v1/edit-groups/1/dump-editset/" --download-trial="http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000/api/v1/edit-groups/26/dump-editset/"
```

For each execution (`run-edit-set`), a `job` is made via the toolforge `jobs` framework.

_Note: this requires having access to the `jobs` & kubernetes API from your local environment_

### `run-edit-set`

This does all the heavy lifting for a specific edit group, executing the `steps` required for training.

Example local execution:

```
cbng-trainer run-edit-set --image-name="tools-harbor.wmcloud.org/tool-cluebotng-trainer/trainer:latest" --target-name="Legacy Report Interface Import" --instance-name="2025-08-03 22:56:16" --release-ref="v1.0.3" --trainer-host="http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000" --download-training="http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000/api/v1/edit-groups/1/dump-editset/" --download-trial="http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000/api/v1/edit-groups/26/dump-editset/"
INFO:cbng_trainer.common.toolforge:Starting job legacy-report-interface-import-store-edit-sets
INFO:cbng_trainer.common.toolforge:Job is running, but container is not...
INFO:cbng_trainer.common.toolforge:Container has actually started...
INFO:cbng_trainer.common.toolforge:Job is no longer running...
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + curl --fail --progress-bar -sL --output /tmp/2aaea9db5d82477f9d33512db3a65ddd http://cluebotng-review.tool-cluebotng-review.svc.tools.local:8000/api/v1/edit-groups/1/dump-editset/
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + upload_file /tmp/2aaea9db5d82477f9d33512db3a65ddd http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000/Legacy%20Report%20Interface%20Import/2025-08-03%2022%3A56%3A16/edit-sets/train.xml
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + source_path=/tmp/2aaea9db5d82477f9d33512db3a65ddd
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + target_url=http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000/Legacy%20Report%20Interface%20Import/2025-08-03%2022%3A56%3A16/edit-sets/train.xml
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + '[' -s /tmp/2aaea9db5d82477f9d33512db3a65ddd ']'
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] + curl --fail -H@/tmp/file-api-headers --data-binary @/tmp/2aaea9db5d82477f9d33512db3a65ddd http://cluebotng-trainer.tool-cluebotng-trainer.svc.tools.local:8000/Legacy%20Report%20Interface%20Import/2025-08-03%2022%3A56%3A16/edit-sets/train.xml
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw]   % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw]                                  Dload  Upload   Total   Spent    Left  Speed
INFO:cbng_trainer.common.toolforge:[legacy-report-interface-import-store-edit-sets-mlnxw] 
INFO:__main__:Running bayes train
INFO:cbng_trainer.common.toolforge:Starting job legacy-report-interface-import-bayes-train
INFO:cbng_trainer.common.toolforge:Job is running, but container is not...
INFO:cbng_trainer.common.toolforge:Container has actually started...
[...]
```

For each step, a `job` is made via the toolforge `jobs` framework.

_Note: this requires having access to the `jobs` & kubernetes API from your local environment_

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
