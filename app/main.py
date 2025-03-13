import sys
import os
import zlib
import hashlib


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
            object_type, content = decompressed.split(b"\0", maxsplit=1)
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

    else:
        raise RuntimeError(f"Unknown command #{command}")


if __name__ == "__main__":
    main()
