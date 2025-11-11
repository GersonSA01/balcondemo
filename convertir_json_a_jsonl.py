"""
Script para convertir un archivo JSON (array) a JSONL (una línea por objeto)
Esto es más eficiente para procesar archivos grandes ya que permite lectura línea por línea.
"""
import json
import argparse
from pathlib import Path

def convert_json_to_jsonl(input_file: str, output_file: str):
    """Convierte un archivo JSON array a JSONL"""
    print(f"Leyendo {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Total de objetos: {len(data)}")
    print(f"Escribiendo a {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, item in enumerate(data):
            json.dump(item, f, ensure_ascii=False)
            f.write('\n')
            if (i + 1) % 10000 == 0:
                print(f"  Procesados: {i + 1}/{len(data)}")
    
    print(f"✅ Conversión completada: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convierte JSON array a JSONL")
    parser.add_argument("--input", required=True, help="Archivo JSON de entrada")
    parser.add_argument("--output", help="Archivo JSONL de salida (si no se especifica, usa .jsonl)")
    
    args = parser.parse_args()
    
    if args.output:
        output_file = args.output
    else:
        output_file = str(Path(args.input).with_suffix('.jsonl'))
    
    convert_json_to_jsonl(args.input, output_file)

