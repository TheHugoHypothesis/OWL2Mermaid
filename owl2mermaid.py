import os
import re
import sys
import requests
import tempfile
import argparse
from urllib.parse import urlparse
from owlready2 import *

# ========= CLASSES E LÓGICA =========

class OntologyMapper:
    def __init__(self):
        self.loaded_ontologies = {}
        self.namespace_map = {}
        self.prefix_counter = 0

    def normalize_id(self, name):
        return re.sub(r'[^a-zA-Z0-9_]', '_', str(name))

    def get_label(self, cls):
        if hasattr(cls, "label") and cls.label:
            return str(cls.label[0]).replace('"', "'")
        return cls.name.replace("_", " ")

    def register_namespace(self, onto):
        base = onto.base_iri
        if base not in self.namespace_map:
            parsed = urlparse(base)
            name = parsed.path.split("/")[-1] or parsed.netloc.split(".")[0]
            prefix = re.sub(r'[^a-zA-Z]', '', name.lower()) or f"ns{self.prefix_counter}"
            self.namespace_map[base] = prefix
            self.prefix_counter += 1

    def download_to_temp(self, url):
        try:
            print(f"🌐 Baixando: {url}")
            headers = {'Accept': 'application/rdf+xml, application/xml'}
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".owl", mode='w', encoding='utf-8') as tmp:
                tmp.write(r.text)
                return tmp.name
        except Exception as e:
            print(f"❌ Erro ao baixar {url}: {e}")
            return None

    def load_ontology(self, path_or_iri, recursive_list=None):
        """Carrega a ontologia. Se recursive_list for None, não carrega imports automaticamente."""
        if path_or_iri in self.loaded_ontologies:
            return self.loaded_ontologies[path_or_iri]

        is_url = path_or_iri.startswith("http")
        try:
            if is_url:
                target = self.download_to_temp(path_or_iri)
            else:
                target = os.path.abspath(path_or_iri)

            if not target: return None

            onto = get_ontology(f"file://{target}").load()
            self.loaded_ontologies[path_or_iri] = onto
            self.register_namespace(onto)

            # Se houver uma lista de IRIs permitidas, carrega apenas elas
            if recursive_list:
                for imp in onto.imported_ontologies:
                    if imp.base_iri in recursive_list:
                        self.load_ontology(imp.base_iri, recursive_list)

            return onto
        except Exception as e:
            print(f"⚠️ Falha ao carregar {path_or_iri}: {e}")
            return None

    def save_mermaid(self, filename="output.mmd"):
        all_classes = set()
        for onto in self.loaded_ontologies.values():
            all_classes.update(onto.classes())

        groups = {}
        edges = []

        for cls in all_classes:
            # Tenta determinar prefixo/namespace
            prefix = "other"
            for base, p in self.namespace_map.items():
                if cls.iri.startswith(base):
                    prefix = p
                    break

            groups.setdefault(prefix, []).append(cls)
            for parent in cls.is_a:
                if isinstance(parent, ThingClass) and parent in all_classes:
                    edges.append((parent, cls))

        with open(filename, "w", encoding="utf-8") as f:
            f.write("---\ntitle: Ontology Visualization\nconfig:\n  look: neo\n  layout: elk\n---\n")
            f.write("flowchart BT\n")

            colors = ["#e3f2fd", "#e8f5e9", "#fff3e0", "#f3e5f5", "#ede7f6", "#e0f7fa"]
            for i, (prefix, color) in enumerate(zip(groups.keys(), colors * 5)):
                f.write(f"    classDef {prefix} fill:{color},stroke:#333,stroke-width:1,color:#000;\n")

            for prefix, classes in groups.items():
                f.write(f"\n    subgraph {prefix.upper()}\n        direction BT\n")
                for cls in classes:
                    f.write(f'        {self.normalize_id(cls.name)}["{self.get_label(cls)}"]\n')
                f.write("    end\n")

            for parent, child in set(edges):
                f.write(f"    {self.normalize_id(child.name)} --> {self.normalize_id(parent.name)}\n")

            for prefix, classes in groups.items():
                for cls in classes:
                    f.write(f"    class {self.normalize_id(cls.name)} {prefix};\n")

        print(f"\n✅ Sucesso! Arquivo gerado: {os.path.abspath(filename)}")

# ========= INTERFACE DE COMANDO =========

def main():
    parser = argparse.ArgumentParser(description="OWL to Mermaid Converter v6")
    parser.add_argument("input", help="URL ou Caminho local do arquivo .owl")
    parser.add_argument("--out", default="ontology_diagram.mmd", help="Nome do arquivo de saída")
    args = parser.parse_args()

    mapper = OntologyMapper()

    print(f"🧐 Analisando ontologia principal...")
    # Carregamento inicial sem recursão forçada para listar imports
    base_onto = mapper.load_ontology(args.input)

    if not base_onto:
        sys.exit(1)

    # Identificar imports disponíveis
    available_imports = [imp.base_iri for imp in base_onto.imported_ontologies]

    selected_iris = []
    if available_imports:
        print("\n📥 Esta ontologia possui as seguintes importações disponíveis:")
        for idx, iri in enumerate(available_imports, 1):
            print(f"  [{idx}] {iri}")

        print("\nDigite os números das ontologias que deseja incluir (ex: 1,3) ou pressione ENTER para nenhuma:")
        choice = input(">> ").strip()

        if choice:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected_iris = [available_imports[i] for i in indices if 0 <= i < len(available_imports)]

                print(f"🔄 Carregando dependências selecionadas...")
                for iri in selected_iris:
                    mapper.load_ontology(iri)
            except Exception as e:
                print(f"❌ Seleção inválida. Processando apenas a base.")

    # Gerar o arquivo final
    mapper.save_mermaid(args.out)

if __name__ == "__main__":
    main()
