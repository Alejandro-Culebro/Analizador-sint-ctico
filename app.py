import re
from flask import Flask, request, render_template_string, redirect, url_for

app = Flask(__name__)

# --------------------------
# Analizador Léxico
# --------------------------
RESERVADAS = {
    'programa', 'int', 'float', 'double', 'char', 'void',
    'for', 'while', 'if', 'else',
    'read', 'printf', 'end', 'return', 'system', 'print'
}

def analizar_lexico(codigo: str):
    token_specs = [
        ('LINE_COMMENT',    r'//[^\n]*'),               # comentarios de línea
        ('NUMERO',          r'\d+(\.\d+)?'),
        ('CADENA',          r'"[^"\n]*"'),
        ('IDENTIFICADOR',   r'[A-Za-z_]\w*'),
        ('SIMBOLO',         r'<=|>=|==|!=|\+\+|--|[=+\-*/%<>]'),
        ('DELIMITADOR',     r'[;(),{}\.\[\]]'),
        ('ESPACIO',         r'\s+'),
        ('DESCONOCIDO',     r'.'),
    ]
    regex_tokens = '|'.join(f'(?P<{t}>{p})' for t, p in token_specs)

    tokens = []
    linea = 1
    col_base = 0
    lineas = codigo.splitlines(keepends=True)

    for m in re.finditer(regex_tokens, codigo):
        tipo = m.lastgroup
        lexema = m.group(0)

        # Línea/columna
        while linea-1 < len(lineas) and m.start() >= col_base + len(lineas[linea-1]):
            col_base += len(lineas[linea-1])
            linea += 1
        columna = m.start() - col_base + 1

        # ignorar espacios y comentarios
        if tipo in ('ESPACIO', 'LINE_COMMENT'):
            continue

        if tipo == 'IDENTIFICADOR' and lexema.lower() in RESERVADAS:
            tipo = 'PALABRA_RESERVADA'

        tokens.append({"tipo": tipo, "lexema": lexema, "linea": linea, "columna": columna})
    return tokens

# --------------------------
# Analizador Sintáctico (gramática simple)
# --------------------------
class Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0
        self.err = []

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if 0 <= j < len(self.t) else None

    def match(self, tipo=None, lexema=None, msg=None):
        tok = self.peek()
        if tok and (tipo is None or tok['tipo'] == tipo) and (lexema is None or tok['lexema'] == lexema):
            self.i += 1
            return tok
        # error
        esperado = []
        if tipo: esperado.append(tipo)
        if lexema: esperado.append(f"'{lexema}'")
        got = "EOF" if tok is None else f"{tok['tipo']}('{tok['lexema']}')"
        if msg is None:
            msg = f"Se esperaba {' y '.join(esperado)} pero se encontró {got} (línea {tok['linea'] if tok else '-'})."
        self.err.append(msg)
        # tratar de avanzar para no quedar bloqueados
        if tok: self.i += 1
        return None

    # ---- Gramática ----
    # programa := 'programa' IDENT '(' ')' '{' stmt* '}' ;
    def parse_programa(self):
        self.match('PALABRA_RESERVADA', 'programa', "Se esperaba la palabra 'programa' al inicio.")
        self.match('IDENTIFICADOR', None, "Falta el nombre del programa después de 'programa'.")
        self.match('DELIMITADOR', '(', "Falta '(' después del nombre del programa.")
        self.match('DELIMITADOR', ')', "Falta ')' después del nombre del programa.")
        self.match('DELIMITADOR', '{', "Falta '{' para abrir el bloque del programa.")
        while self.peek() and not (self.peek()['tipo']=='DELIMITADOR' and self.peek()['lexema']=='}'):
            self.parse_stmt()
        self.match('DELIMITADOR', '}', "Falta '}' para cerrar el programa.")

    # stmt := decl | read | printf | assign | endstmt ;
    def parse_stmt(self):
        tok = self.peek()
        if not tok:
            self.err.append("Fin inesperado dentro del bloque.")
            return
        if tok['tipo']=='PALABRA_RESERVADA' and tok['lexema']=='int':
            self.parse_decl()
        elif tok['tipo']=='PALABRA_RESERVADA' and tok['lexema']=='read':
            self.parse_read()
        elif tok['tipo']=='PALABRA_RESERVADA' and tok['lexema']=='printf':
            self.parse_printf()
        elif tok['tipo']=='PALABRA_RESERVADA' and tok['lexema']=='end':
            self.i += 1
            self.match('DELIMITADOR', ';', "Después de 'end' debe ir ';'.")
        elif tok['tipo']=='IDENTIFICADOR':
            self.parse_assign()
        else:
            self.err.append(f"Sentencia no válida iniciando en {tok['tipo']}('{tok['lexema']}') (línea {tok['linea']}).")
            self.i += 1  # avanzar para no ciclar

    # decl := 'int' id (',' id)* ';'
    def parse_decl(self):
        self.match('PALABRA_RESERVADA', 'int')
        self.match('IDENTIFICADOR', None, "Se esperaba un identificador en la declaración.")
        while self.peek() and self.peek()['tipo']=='DELIMITADOR' and self.peek()['lexema']==',':
            self.i += 1
            self.match('IDENTIFICADOR', None, "Se esperaba un identificador después de ','.")
        self.match('DELIMITADOR', ';', "Falta ';' al final de la declaración.")

    # read := 'read' IDENT ';'
    def parse_read(self):
        self.match('PALABRA_RESERVADA', 'read')
        self.match('IDENTIFICADOR', None, "Se esperaba un identificador después de 'read'.")
        self.match('DELIMITADOR', ';', "Falta ';' después de la instrucción 'read'.")

    # printf := 'printf' '(' CADENA ')' ';'
    def parse_printf(self):
        self.match('PALABRA_RESERVADA', 'printf')
        self.match('DELIMITADOR', '(', "Falta '(' en printf.")
        self.match('CADENA', None, "Falta la cadena dentro de printf.")
        self.match('DELIMITADOR', ')', "Falta ')' al cerrar printf.")
        self.match('DELIMITADOR', ';', "Falta ';' al final de printf.")

    # assign := IDENT '=' expr ';'
    def parse_assign(self):
        self.match('IDENTIFICADOR')
        self.match('SIMBOLO', '=', "Falta '=' en la asignación.")
        self.parse_expr()
        self.match('DELIMITADOR', ';', "Falta ';' al final de la asignación.")

    # expr := term (('+'|'-') term)*
    def parse_expr(self):
        self.parse_term()
        while self.peek() and self.peek()['tipo']=='SIMBOLO' and self.peek()['lexema'] in ('+','-'):
            self.i += 1
            self.parse_term()

    # term := factor (('*'|'/') factor)*
    def parse_term(self):
        self.parse_factor()
        while self.peek() and self.peek()['tipo']=='SIMBOLO' and self.peek()['lexema'] in ('*','/'):
            self.i += 1
            self.parse_factor()

    # factor := IDENT | NUMERO | '(' expr ')'
    def parse_factor(self):
        tok = self.peek()
        if not tok:
            self.err.append("Expresión incompleta.")
            return
        if tok['tipo'] in ('IDENTIFICADOR','NUMERO'):
            self.i += 1
            return
        if tok['tipo']=='DELIMITADOR' and tok['lexema']=='(':
            self.i += 1
            self.parse_expr()
            self.match('DELIMITADOR', ')', "Falta ')' para cerrar la expresión.")
            return
        self.err.append(f"Factor inválido en la expresión: {tok['tipo']}('{tok['lexema']}') (línea {tok['linea']}).")
        self.i += 1

def analizar_sintactico(codigo: str, tokens):
    p = Parser(tokens)
    p.parse_programa()
    # si sobran tokens después de '}', repórtalos
    if p.i < len(tokens):
        tok = tokens[p.i]
        p.err.append(f"Tokens extra después de cerrar el programa, empezando en '{tok['lexema']}' (línea {tok['linea']}).")
    return {"correcto": len(p.err) == 0, "errores": p.err}

# --------------------------
# Web (igual que antes, sólo usa el nuevo parser)
# --------------------------
TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Analizador Léxico y Sintáctico</title>
<style>
  *{box-sizing:border-box}
  body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;margin:24px;color:#2d3436}
  h1{margin:0 0 8px}
  .muted{color:#636e72;font-size:14px;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:1.1fr 1.4fr;gap:16px;align-items:start}
  textarea{width:100%;min-height:360px;padding:12px;border:1px solid #dfe6e9;border-radius:10px;font-size:15px;background:#fff}
  .panel{background:#fff;border:1px solid #dfe6e9;border-radius:10px;padding:12px;overflow:auto;max-height:520px}
  table{border-collapse:collapse;width:100%}
  th,td{border:1px solid #ecf0f1;padding:8px;text-align:center;font-size:14px}
  th{background:#34495e;color:#fff;position:sticky;top:0}
  td:first-child{text-align:left;font-weight:600}
  .btns{margin-top:10px;display:flex;gap:10px;flex-wrap:wrap}
  button{border:0;border-radius:10px;padding:10px 14px;cursor:pointer;font-weight:600}
  .lex{background:#2980b9;color:#fff}
  .sin{background:#27ae60;color:#fff}
  .clr{background:#e74c3c;color:#fff}
  .ok{color:#27ae60;font-weight:700}
  .err{color:#c0392b}
</style>
</head>
<body>
  <h1>Analizador Léxico y Sintáctico</h1>
  

  <form method="POST">
    <div class="grid">
      <div>
        <textarea name="codigo" placeholder="Ejemplo:
programa suma(){
  int a,b,c;
  read a;
  read b;
  c = a + b;
  printf(&quot;la suma es&quot;);
  end;
}">{{ codigo }}</textarea>
        <div class="btns">
          <button class="lex" name="accion" value="lexico">Análisis Léxico</button>
          <button class="sin" name="accion" value="sintactico">Análisis Sintáctico</button>
          <button class="clr" name="accion" value="borrar">Borrar</button>
        </div>
      </div>

      <div class="panel">
        {% if resultado %}
        <h3>Tabla de Tokens</h3>
        <table>
          <tr>
            <th>TOKEN</th><th>PR</th><th>ID</th><th>CAD</th><th>NU</th><th>SI</th><th>TIPO</th>
          </tr>
          {% for t in resultado %}
          <tr>
            <td>{{ t.lexema }}</td>
            <td>{% if t.tipo == 'PALABRA_RESERVADA' %}X{% endif %}</td>
            <td>{% if t.tipo == 'IDENTIFICADOR' %}X{% endif %}</td>
            <td>{% if t.tipo == 'CADENA' %}X{% endif %}</td>
            <td>{% if t.tipo == 'NUMERO' %}X{% endif %}</td>
            <td>{% if t.tipo in ['SIMBOLO','DELIMITADOR'] %}X{% endif %}</td>
            <td>{{ t.tipo }}</td>
          </tr>
          {% endfor %}
        </table>

        <h3>Resumen</h3>
        <table>
          <tr>
            <th>PR</th><th>ID</th><th>DEL</th><th>SI</th><th>NU</th><th>Total</th>
          </tr>
          <tr>
            <td>{{ resumen.PR }}</td>
            <td>{{ resumen.ID }}</td>
            <td>{{ resumen.PD }}</td>
            <td>{{ resumen.Simb }}</td>
            <td>{{ resumen.Num }}</td>
            <td>{{ resumen.Total }}</td>
          </tr>
        </table>
        {% endif %}

        {% if mostrado_sintactico %}
        <h3>Resultado del Análisis Sintáctico</h3>
        {% if sintactico.correcto %}
          <p class="ok">Sintáctico Correcto</p>
        {% else %}
          <ul>
            {% for e in sintactico.errores %}<li class="err">{{ e }}</li>{% endfor %}
          </ul>
        {% endif %}
        {% endif %}
      </div>
    </div>
  </form>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    codigo = ""
    resultado = []
    resumen = {"PR": 0, "ID": 0, "PD": 0, "Simb": 0, "Num": 0, "Total": 0}
    sintactico = {"correcto": False, "errores": []}
    mostrado_sintactico = False

    if request.method == 'POST':
        accion = request.form.get('accion')
        codigo = request.form.get('codigo', '')

        if accion == 'borrar':
            return redirect(url_for('index'))

        if codigo:
            resultado = analizar_lexico(codigo)
            for token in resultado:
                if token["tipo"] == "PALABRA_RESERVADA": resumen["PR"] += 1
                elif token["tipo"] == "IDENTIFICADOR":    resumen["ID"] += 1
                elif token["tipo"] == "DELIMITADOR":      resumen["PD"] += 1
                elif token["tipo"] == "SIMBOLO":          resumen["Simb"] += 1
                elif token["tipo"] == "NUMERO":           resumen["Num"] += 1
            resumen["Total"] = len(resultado)

            if accion == 'sintactico':
                mostrado_sintactico = True
                sintactico = analizar_sintactico(codigo, resultado)

    return render_template_string(
        TEMPLATE,
        codigo=codigo,
        resultado=resultado,
        resumen=resumen,
        sintactico=sintactico,
        mostrado_sintactico=mostrado_sintactico
    )

if __name__ == '__main__':
    app.run(debug=True)
