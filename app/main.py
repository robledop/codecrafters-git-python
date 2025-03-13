import sys
import os
import zlib


def main():
    command = sys.argv[1]
    if command == "init":
        os.mkdir(".git")
        os.mkdir(".git/objects")
        os.mkdir(".git/refs")
        with open(".git/HEAD", "w") as f:
            f.write("ref: refs/heads/main\n")
        print("Initialized git directory")
    elif command == "cat-file":
        cat_file_arg = sys.argv[2]
        if cat_file_arg == "-p":
            object_hash = sys.argv[3]
            # The first 2 char of hash is the folder, and the remaining is the file name
            path = f".git/objects/{object_hash[:2]}/{object_hash[2:]}"
            with open(path, "rb") as f:
                decompressed = zlib.decompress(f.read())
                text = decompressed.decode("utf-8")
                parts = text.split(" ")
                object_type = parts[0]
                if object_type == "blob":
                    object_size = int(parts[1].split("\0")[0])
                    start = text.index("\0") + 1
                    content = text[start : start + object_size]
                    print(content, end="")

    else:
        raise RuntimeError(f"Unknown command #{command}")


if __name__ == "__main__":
    main()
