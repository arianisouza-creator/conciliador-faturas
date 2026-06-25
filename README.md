# Conciliacao de Cartao

Aplicacao em Streamlit para ler a fatura do cartao e cruzar com PDFs de apoio, como planilhas de hospedagem ou relatorios com pedido/localizador.

## O que faz

- Le a fatura em PDF.
- Detecta os titulares encontrados na fatura.
- Extrai os lancamentos do titular escolhido.
- Le um ou mais PDFs de apoio.
- Tenta conciliar por localizador, valor e data.
- Gera saida em PDF, Excel e CSV.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run conciliacao_cartao.py
```

## Arquivos esperados

- Fatura em PDF
- Um ou mais PDFs de apoio

## Observacoes

- Se o PDF for escaneado como imagem, `pypdf` pode nao conseguir extrair o texto.
- O app usa o valor final da linha como referencia principal e melhora a conciliacao com a data quando ela existe.
- Quando houver mais de um pedido com o mesmo valor, o lancamento pode aparecer como `AMBIGUO`.
