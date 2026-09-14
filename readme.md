# MEA-EB5 Runner

Este é o repositório visível ao engenheiro que executará o MEA. Ele contém os
cinco desafios públicos, o runner isolado e o workflow de tentativa. Testes
ocultos, soluções de controle, score oficial e publicação ficam no repositório
privado do avaliador.

## Preparar o MEA

1. Publique o MEA como imagem OCI e obtenha o digest `sha256` imutável.
2. Copie `mea.adapter.example.yaml` para `mea.adapter.yaml`.
3. Substitua `image` pelo nome e digest reais.
4. Ajuste `command`. O runner acrescenta `--goal-file /workspace/.mea-eb5-goal.txt`.

O contêiner recebe somente `/workspace`, sem rede, sem Docker socket, sem
secrets, como usuário não privilegiado e com limites de CPU, memória e PIDs.

## Executar rapidamente

No GitHub, abra **Actions → Benchmark attempts → Run workflow** e escolha:

- `profile: smoke`
- `adapter: cli`
- `adapter_config: mea.adapter.yaml`
- `challenge: all`

O smoke executa os cinco desafios em paralelo, com uma seed por desafio. O
perfil `release` executa 25 jobs: cinco desafios × cinco seeds. Cada job gera um
arquivo de evidência preservado por 14 dias. Envie o ID numérico do workflow ao
responsável pelo repositório privado de avaliação.

## Limite de confiança

O resultado deste workflow não é aprovação oficial. Ele registra tentativa,
logs, patch, testes públicos, duração, hashes e manifesto. A classificação
oficial só aparece depois da avaliação privada e tem
`grader_provenance: INDEPENDENT`.
