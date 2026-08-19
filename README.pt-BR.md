# PyCUPS

**CUPS Archive para trabalhos de impressão retidos.**

PyCUPS é um aplicativo leve em GTK 4 e Libadwaita para Ubuntu e outros
sistemas GNOME baseados em Debian. Ele usa o serviço CUPS local para consultar
o histórico, obter os documentos de impressão retidos, pré-visualizá-los,
exportá-los e reimprimir o trabalho inteiro ou páginas selecionadas de um PDF.

O projeto segue os moldes do PyNextCloud Sync: aplicativo nativo de
instância única, núcleo Python pequeno e testável, projeto Meson, pacote `.deb`,
ZIP com o código-fonte, tradução para português do Brasil e nenhuma senha
administrativa armazenada pelo aplicativo.

Repositório do projeto: <https://github.com/ehstbr/PyCUPS>

## Principais recursos

- Busca no histórico e filtro por estado, todas as impressoras ou qualquer
  combinação de impressoras marcada por checkboxes.
- Atualização automática do histórico a cada 10 segundos para que jobs novos
  apareçam sem reabrir o aplicativo.
- Pré-visualização paginada de PDF e visualização de imagens e textos comuns.
- Reinício exato do job ao escolher todas as páginas, uma cópia e a impressora
  original.
- Reimpressão de páginas de PDF usando expressões como `3`, `2-5` ou
  `1,4,7-10`. O aplicativo cria temporariamente um novo PDF contendo apenas as
  páginas pedidas e o envia como um novo job.
- Escolha de outra impressora, papel, escala e número de cópias, com preview da
  folha de destino baseado nas capacidades informadas pelo CUPS.
- Exportação do documento retido sem acessar `/var/spool/cups` diretamente.
- Exclusão permanente de um job ou de todo o histórico, sempre com confirmação.
- Abas Retenção, Servidor e Manutenção para retenção e opções globais limitadas
  do CUPS, sempre por uma solicitação administrativa nativa do PolicyKit.
- Assistente inicial em três etapas para apresentar a privacidade e comparar os
  valores atuais do CUPS com uma sugestão de retenção editável.
- Verificação de um manifesto validado no GitHub ao iniciar ou sob demanda,
  com o mesmo comportamento opcional/obrigatório do PyNextCloud Sync.

## Boas-vindas e privacidade na primeira execução

A primeira execução apresenta três páginas: introdução sobre privacidade e
código aberto, proposta editável de retenção e resumo de conclusão. O PyCUPS não
envia documentos retidos nem metadados de jobs para a internet. Sua única
requisição automática lê no GitHub o pequeno manifesto de versões; nenhum
conteúdo de impressão faz parte dessa comunicação.

A página da proposta lê a configuração real do CUPS antes de habilitar
**Aplicar e continuar**. **Pular sem alterar** mantém todos os valores atuais.
O fluxo pode ser aberto novamente em **Boas-vindas e configuração inicial** no
menu principal.

Somente um indicador de conclusão é salvo na pasta de configuração XDG do
usuário, normalmente em `~/.config/pycups/state.json`. Esse arquivo não contém
valores do CUPS, nomes de documentos, metadados, credenciais ou impressões.

## A configuração de retenção nunca é automática

Instalar, atualizar ou abrir o PyCUPS não altera a configuração do
CUPS. A tela de configurações primeiro lê os valores que estão sendo usados
pelo computador. Se essa leitura falhar, os controles permanecem desativados,
evitando que uma configuração desconhecida seja sobrescrita por acidente.

Uma mudança só acontece depois que o usuário edita os campos, pressiona
**Aplicar** e autoriza a operação pelo PolicyKit. O assistente inicial oferece
o seguinte equilíbrio editável:

| Diretiva do CUPS | Valor | Resultado |
|---|---:|---|
| `PreserveJobFiles` | `2592000` | Mantém arquivos reimprimíveis por 30 dias. |
| `PreserveJobHistory` | `7776000` | Mantém os metadados por 90 dias. |
| `MaxJobs` | `0` | Não impõe limite pela quantidade de jobs. |

Depois de salvar configurações de retenção ou do servidor global, o PyCUPS
mostra o diálogo bloqueante **Reiniciando CUPS…**. Ele pausa a atualização do
histórico, cria novas conexões IPP até obter várias respostas consecutivas e só
então libera a interface e recarrega os jobs. Se o serviço continuar
indisponível, o diálogo mantém o aplicativo bloqueado e inicia outra sondagem
automaticamente. **Tentar novamente** solicita uma tentativa imediata, enquanto
**Fechar o PyCUPS** oferece uma saída segura se o serviço não se recuperar.

Esses são valores sugeridos no formulário, não padrões do pacote ou da
inicialização. Os prazos finitos equilibram a recuperação de impressões recentes
com a privacidade; `MaxJobs=0` evita que um limite por quantidade encurte esses
prazos. Os padrões documentados do CUPS são diferentes: arquivo retido por 86.400
segundos (um dia), histórico de metadados ativado sem prazo e `MaxJobs=500`.
Portanto, um `MaxJobs` finito pode eliminar entradas antigas antes de vencer um
prazo longo em dias.

A aba Retenção também oferece **Sem limite de tempo para os arquivos**, que
envia `PreserveJobFiles=Yes`. Isso continua sujeito à remoção de jobs pelo
`MaxJobs`; combine com `MaxJobs=0` somente acompanhando o uso do disco.

## Instalação no Ubuntu

Instale o pacote Debian fornecido:

```bash
sudo apt install ./print-archive_0.1.10_all.deb
```

Depois, abra **PyCUPS** na grade de aplicativos ou execute:

```bash
print-archive
```

Para executar diretamente pelo código-fonte:

```bash
sudo apt install python3 python3-gi python3-cups python3-pypdf \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-soup-3.0 \
  poppler-utils cups-client cups-daemon pkexec gettext
./run.sh
```

## Como reimprimir somente uma página de dez

Supondo que o job 42 tenha 10 páginas:

1. Selecione o job 42 e aguarde a pré-visualização.
2. Clique em **Reimprimir…**.
3. Desative **Reiniciar exatamente o job original** e **Imprimir todas as páginas**.
4. Digite `4` para imprimir apenas a página 4. Também é possível usar
   `1,4,7-10`, por exemplo.
5. Escolha impressora, papel, escala e cópias, confira o preview e clique em
   **Imprimir**.

O job de origem não é modificado. O PDF extraído e as imagens de
pré-visualização ficam em um diretório temporário privado, com permissão `0700`;
os arquivos usam `0600` e tudo é removido ao fechar o aplicativo.

## Reinício exato e reimpressão flexível

- **Reinício exato:** ative o seletor de reinício exato. O CUPS reinicia todas
  as páginas, uma cópia, na impressora original e conserva as opções retidas.
- **Reimpressão flexível:** páginas selecionadas, várias cópias ou outra
  impressora. Um novo job é criado com cópias, palavra-chave do papel e
  `print-scaling`. Frente e verso, acabamento, cor e outras opções do job antigo
  não são clonados.
- **Preview da folha de destino:** para PDF, o aplicativo monta uma aproximação
  com dimensões, margens imprimíveis e escala informadas via IPP. O driver ainda
  pode fazer ajustes próprios do equipamento.
- **Formatos crus/térmicos:** podem ser reiniciados integralmente caso tenham
  sido retidos, mas não podem ser visualizados nem divididos nesta versão.
- **Vários documentos:** se todos forem PDF, eles são combinados para a
  visualização e seleção. Formatos mistos permitem apenas o reinício exato.

## Permissões e privacidade

O PyCUPS usa os bindings Python PyCUPS do sistema e operações IPP em vez de ler
a pasta privada de spool. Conforme a política do servidor, o CUPS pode permitir a obtenção,
reimpressão ou exclusão apenas ao proprietário do job ou a um administrador de
impressão. Quando uma dessas operações exige autenticação, o PyCUPS
solicita o usuário e a senha do Ubuntu/CUPS, entrega-os ao callback do PyCUPS,
limpa o campo da senha e não salva a credencial.

Para mudar retenção ou opções globais, o pacote instala o auxiliar protegido
`/usr/lib/print-archive/apply-settings`. Ele aceita somente três valores de
retenção validados ou seis opções globais `sim/não` e executa `cupsctl`. O
PolicyKit pede a autenticação administrativa;
essa senha de configuração permanece dentro do PolicyKit e o aplicativo não a
recebe nem a guarda.

Arquivos impressos podem conter informações confidenciais. Reter os arquivos
por 30 dias, o histórico por 90 dias e usar `MaxJobs=0` ainda pode consumir
bastante espaço em sistemas movimentados. Monitore o armazenamento do spool e
personalize a proposta quando o computador tiver pouco espaço.

## Limitações importantes

- Não é possível recuperar arquivos que o CUPS já expirou ou eliminou.
- Um item pode continuar no histórico depois que seu arquivo reimprimível
  expirar.
- A pré-visualização de PDF requer `pdftoppm`, do pacote `poppler-utils`.
- PDFs criptografados ou danificados podem não ser visualizados ou divididos.
- A versão 0.1.10 trabalha com o CUPS local. As configurações são globais para
  esse serviço; o aplicativo propositalmente não gerencia impressoras individuais.
- O preview depende das capacidades IPP informadas pelo destino e não consegue
  prever todo ajuste específico do driver ou do equipamento.

## Desenvolvimento e testes

```bash
./tools/run-tests.sh
meson setup build
meson compile -C build
```

## Licença

Copyright © 2026 EduhCommerce. GNU GPL versão 3 ou posterior.
