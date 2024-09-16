Na minha visão o endpoint proposto para esse teste deveria apenas ser responsável pelo upload do arquivo CSV.
Dessa forma o usuário não precisaria de esperar que o processamento da informação acontecesse de maneira síncrona.

Por sua vez, uma rotina async no servidor seria responsável por identificar novos arquivos que tivessem sido upados e realizaria o processamento das informações tais como o envio de emails e geração de PDFs.

Não foi possível concluir em tempo hábil os testes unitários por falta de tempo e devido a complexidade adicionada pelo multiprocessamento utilizado no endpoint.

Para executar o projeto
    - docker-compose build --no-cache
    - docker compose up

Para executar os testes unitários basta rodar o pytest no diretório raiz /app
    - docker exec -it <docker-id>
    - pytest
