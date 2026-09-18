# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent

conteudo = r'''{% extends "base.html" %}
{% block titulo %}Registrar Movimentação{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Registrar Movimentação</h1>
    <p class="page-sub">Cadastre a movimentação de um bem entre setores</p>
  </div>
</div>

<form class="card grid" action="/registrar" method="POST">
  <div class="campo">
    <label>Funcionário responsável</label>
    <select name="funcionario" required>
      <option value="">Selecione um funcionário</option>
      {% for f in funcionarios %}
        <option value="{{ f.nome }}">{{ f.nome }}{% if f.cargo %} — {{ f.cargo }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem / Item</label>
    <select name="bem" required>
      <option value="">Selecione um bem</option>
      {% for b in bens %}
        <option value="{{ b.patrimonio }}">{{ b.patrimonio }} — {{ b.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Local de origem</label>
    <select name="origem" required>
      <option value="">Selecione o local de origem</option>
      {% for l in locais %}
        <option value="{{ l.nome }}">{{ l.nome }}{% if l.andar %} — {{ l.andar }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino" required>
      <option value="">Selecione o destino</option>
      {% for l in locais %}
        <option value="{{ l.nome }}">{{ l.nome }}{% if l.andar %} — {{ l.andar }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo full">
    <label>Observação (opcional)</label>
    <textarea name="observacao" rows="2" placeholder="Ex: item com avaria, troca de setor, etc."></textarea>
  </div>
  <div class="campo full">
    <button type="submit">Registrar movimentação</button>
  </div>
</form>

<div class="card">
  <div class="card-title">Movimentações por mês</div>
  <div style="height:220px;position:relative;">
    <canvas id="graficoMes"></canvas>
  </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
  <div class="stat-card">
    <div class="stat-label">Total registrado</div>
    <div class="stat-value">{{ total_geral }}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Acesso rápido</div>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
      <a href="/planilha" class="botao secundario pequeno">Ver planilha</a>
      <a href="/historico" class="botao secundario pequeno">Histórico</a>
      <a href="/cadastros" class="botao secundario pequeno">Cadastros</a>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-title">Últimas 10 movimentações</div>
  {% if historico %}
    <table>
      <thead>
        <tr>
          <th>Data/Hora</th><th>Funcionário</th><th>Bem</th>
          <th>Origem</th><th>Destino</th><th>Obs.</th>
        </tr>
      </thead>
      <tbody>
        {% for m in historico %}
          <tr>
            <td>{{ m.data_hora }}</td>
            <td>{{ m.funcionario }}</td>
            <td>{{ m.bem_display }}</td>
            <td>{{ m.origem }}</td>
            <td>{{ m.destino }}</td>
            <td>{{ m.observacao }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p style="color:#64748B;">Nenhuma movimentação registrada ainda.</p>
  {% endif %}
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
  const labels = {{ chart_labels|safe }};
  const valores = {{ chart_valores|safe }};
  const ctx = document.getElementById('graficoMes').getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Movimentações',
        data: valores,
        backgroundColor: '#2563EB',
        hoverBackgroundColor: '#1D4ED8',
        borderRadius: 6,
        maxBarThickness: 28
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            label: (ctx) => ctx.parsed.y + ' movimentação(ões)'
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#64748B', font: { family: 'Inter', size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: '#E2E8F0', drawBorder: false },
          ticks: { color: '#64748B', stepSize: 1, font: { family: 'Inter', size: 11 } }
        }
      }
    }
  });
</script>

{% endblock %}
'''

caminho = BASE / "templates" / "registrar.html"
caminho.write_text(conteudo, encoding="utf-8")
print("[ok]", caminho)
print()
print("=" * 50)
print("Grafico ajustado para 220px de altura.")
print("=" * 50)