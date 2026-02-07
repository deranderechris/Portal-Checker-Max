import os

BASE = "ausgabe"

def fix_missing_extensions():
    if not os.path.exists(BASE):
        print("Ordner 'ausgabe' nicht gefunden.")
        return

    fixed = 0

    for root, dirs, files in os.walk(BASE):
        for file in files:
            # Hat die Datei eine Endung?
            if "." not in file:
                old_path = os.path.join(root, file)

                # Bereinigen
                safe = file.replace(":", "_").replace("/", "_").replace("\\", "_")
                new_path = os.path.join(root, safe + ".html")

                os.rename(old_path, new_path)
                print(f"Fix: {old_path}  →  {new_path}")
                fixed += 1

            # Hat die Datei eine falsche Endung?
            elif not file.lower().endswith(".html"):
                old_path = os.path.join(root, file)
                new_path = os.path.join(root, file + ".html")
                os.rename(old_path, new_path)
                print(f"Fix: {old_path}  →  {new_path}")
                fixed += 1

    print(f"\nFertig. {fixed} Dateien repariert.")

if __name__ == "__main__":
    fix_missing_extensions()
