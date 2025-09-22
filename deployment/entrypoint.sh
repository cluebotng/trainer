#!/bin/bash

if [ "${HOME}" == "/" ] && [ ! -z "${TOOL_DATA_DIR}"];
then
    export HOME="${TOOL_DATA_DIR}"
fi

if [ -f "${HOME}/.kube/config" ];
then
    export KUBECONFIG="${HOME}/.kube/config"
else
    # Generate a minimal k8s config from envvars
    # This avoids needing to mount nfs to get access to the normal tool account
    if [ ! -z "${K8S_CLIENT_CRT}" ] && [ ! -z "${K8S_CLIENT_KEY}" ] && [ ! -z "${K8S_SERVER}" ];
    then
        mkdir -p /workspace/.kube

        echo "${K8S_CLIENT_CRT}" > /workspace/.kube/client.crt
        echo "${K8S_CLIENT_KEY}" > /workspace/.kube/client.key

        cat > /workspace/.kube/config <<EOF
apiVersion: v1
clusters:
- cluster:
    insecure-skip-tls-verify: true
    server: ${K8S_SERVER}
  name: toolforge
contexts:
- context:
    cluster: toolforge
    namespace: tool-cluebotng-trainer
    user: tf-cluebotng-trainer
  name: toolforge
current-context: toolforge
kind: Config
users:
- name: tf-cluebotng-trainer
  user:
    client-certificate: /workspace/.kube/client.crt
    client-key: /workspace/.kube/client.key
EOF

    export KUBECONFIG="/workspace/.kube/config"
    fi
fi

exec python -m cbng_trainer.cli "$@"
