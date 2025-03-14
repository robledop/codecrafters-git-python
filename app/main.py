import enum
import sys
import os
import zlib
import hashlib


class Mode(enum.IntEnum):
    FILE = 100644
    EXECUTABLE = 100755
    SYMLINK = 120000
    DIRECTORY = 40000


class TreeEntry:
    def __init__(self, mode, name, item_hash):
        self.mode = mode
        self.name = name
        self.hash = item_hash


def main():
    command = sys.argv[1]
    if command == "init":
        os.mkdir(".git")
        os.mkdir(".git/objects")
        os.mkdir(".git/refs")
        with open(".git/HEAD", "w") as f:
            f.write("ref: refs/heads/main\n")
        print("Initialized git directory")
    elif command == "cat-file" and sys.argv[2] == "-p":
        object_hash = sys.argv[3]
        # The first 2 chars of the hash is the folder, and the remaining is the file name
        path = f".git/objects/{object_hash[:2]}/{object_hash[2:]}"
        with open(path, "rb") as f:
            decompressed = zlib.decompress(f.read())
            object_header, content = decompressed.split(b"\0", maxsplit=1)
            print(content.decode(encoding="utf-8"), end="")
    elif command == "hash-object" and sys.argv[2] == "-w":
        file_name = sys.argv[3]
        with open(file_name, "r") as f:
            file_content = f.read()
            to_be_hashed = f"blob {len(file_content)}\0{file_content}".encode("utf-8")
            sha_hash = hashlib.sha1(to_be_hashed).hexdigest()
            print(sha_hash, end="")
            folder_path = f".git/objects/{sha_hash[:2]}"
            hashed_file_name = sha_hash[2:]
            if not os.path.exists(folder_path):
                os.mkdir(folder_path)
            with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
                hf.write(zlib.compress(to_be_hashed))
    elif command == "ls-tree":
        tree_hash = sys.argv[3]
        tree_items = []
        with open(f".git/objects/{tree_hash[:2]}/{tree_hash[2:]}", "rb") as f:
            decompressed = zlib.decompress(f.read())
            object_header, content = decompressed.split(b"\0", maxsplit=1)
            if object_header[:4] == b"tree":
                i = 0
                size = int(object_header[5:], 10)
                while i < size:
                    mode_str = content[i:].split(b" ", 1)[0].decode("utf-8")
                    i += len(mode_str) + 1
                    mode = int(mode_str)
                    name = content[i:].split(b"\0", maxsplit=1)[0].decode("utf-8")
                    i += len(name) + 1
                    item_hash = content[i : i + 20]
                    i += 20

                    tree_items.append(TreeEntry(mode, name, item_hash))

            if sys.argv[2] == "--name-only":
                for item in tree_items:
                    print(item.name)
            else:
                for item in tree_items:
                    print(f"{item.mode} ", end="")
                    if item.mode == Mode.DIRECTORY:
                        print("tree ", end="")
                    else:
                        print("blob ", end="")
                    print(item.hash.hex(), end="")
                    print(f"\t{item.name}")

    else:
        raise RuntimeError(f"Unknown command #{command}")


if __name__ == "__main__":
    main()
