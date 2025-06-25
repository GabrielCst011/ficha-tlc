function mostrarCampo(tipo) {
  const campo = document.getElementById('campo-' + tipo);
  if (campo) {
    campo.style.display = 'block';
  }
}

function ocultarCampo(tipo) {
  const campo = document.getElementById('campo-' + tipo);
  if (campo) {
    campo.style.display = 'none';
    const inputs = campo.querySelectorAll('input');
    inputs.forEach(input => input.value = '');
  }
}

function adicionarResponsavel() {
  const container = document.getElementById('responsaveis');

  const novoResponsavel = document.createElement('div');
  novoResponsavel.classList.add('responsavel');

  novoResponsavel.innerHTML = `
    <label>Nome do Responsável:</label>
    <input type="text" name="nome_responsavel[]" required>

    <label>Endereço:</label>
    <input type="text" name="endereco_responsavel[]" required>

    <label>Telefone:</label>
    <input type="tel" name="telefone_responsavel[]" maxlength="11" placeholder="Ex: 11991234567" required>

    <button type="button" onclick="removerResponsavel(this)">Remover responsável</button>
  `;

  container.appendChild(novoResponsavel);
}

function removerResponsavel(botao) {
  const responsavel = botao.parentNode;
  responsavel.remove();
}

document.addEventListener('DOMContentLoaded', () => {
  ['remedio', 'deficiencia', 'mental'].forEach(tipo => {
    const radios = document.getElementsByName({
      remedio: 'remedio_controlado',
      deficiencia: 'deficiencia_locomocao',
      mental: 'condicao_mental'
    }[tipo]);

    let mostrar = false;
    radios.forEach(radio => {
      if (radio.checked && radio.value === 'Sim') mostrar = true;
    });

    if (mostrar) {
      mostrarCampo(tipo);
    } else {
      ocultarCampo(tipo);
    }
  });
});
