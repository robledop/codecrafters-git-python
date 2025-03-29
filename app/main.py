import enum
import sys
import os
import zlib
from hashlib import sha1
import time
import urllib.request
import struct
from pathlib import Path
import re

GIT_AUTHOR_EMAIL = "robledo@test.com"
GIT_AUTHOR_NAME = "Robledo Pazotto"


class ObjectType(enum.Enum):
    COMMIT = 1
    TREE = 2
    BLOB = 3
    TAG = 4
    OFS_DELTA = 6
    REF_DELTA = 7


class Mode(enum.IntEnum):
    FILE = 100644
    EXECUTABLE = 100755
    SYMLINK = 120000
    DIRECTORY = 40000


class TreeEntry:
    def __init__(self, mode, name, item_hash):
        self.mode: Mode = mode
        self.name: str = name
        self.hash: bytes = item_hash
    

def main():
    match sys.argv[1:]:
        case ["init"]:
            init_repo(Path(os.getcwd()))
            
        case ["cat-file" ,"-p", object_hash]:
            cat_file(object_hash)
            
        case ["hash-object" ,write, file_name]:
            sha_hash = hash_file(file_name, write == "-w")
            print(sha_hash, end="")

        case ["ls-tree", param, tree_hash]:
            ls_tree(tree_hash, param)
    
        case ["write-tree"]:
            write_tree()

        case ["commit-tree", tree_sha, "-p", commit_sha, "-m", commit_message]:
            commit_tree(commit_message, commit_sha, tree_sha)

        case ["clone", url_string, dest_dir]:
            clone_repo(dest_dir, url_string)

        case _:
            raise RuntimeError(f"Unknown command #{sys.argv[1:]}")


def clone_repo(dest_dir, url_string):
    print(f"clone {url_string} to {dest_dir}")
    dest_path = Path(dest_dir)
    init_repo(dest_path)
    body = "0014command=ls-refs\n0000"
    req = urllib.request.Request(
        f"{url_string}/git-upload-pack",
        data=body.encode(),
        headers={"git-protocol": "version=2"},
    )
    with urllib.request.urlopen(req) as f:
        data = f.read()
        
    ## Example response
    ##########################################################################
    # 00327b8eb72b9dfa14a28ed22d7618b3cdecaa5d5be0 HEAD\n
    # 003f7b8eb72b9dfa14a28ed22d7618b3cdecaa5d5be0 refs/heads/master\n
    # 0000
    ##########################################################################
    
    refs = extract_references(data.decode())
    
    # Save the references
    for name, sha in refs.items():
        Path(dest_path / ".git" / name).write_text(sha + "\n")
    body = (
            "0011command=fetch0001000fno-progress"
            + "".join("0032want " + sha + "\n" for sha in refs.values())
            + "0009done\n0000"
    )
    
    req = urllib.request.Request(
        f"{url_string}/git-upload-pack",
        data=body.encode(),
        headers={"git-protocol": "version=2"},
    )
    
    with urllib.request.urlopen(req) as f:
        pack_bytes: bytes = f.read()
    lines = []
    while pack_bytes:
        line_len = int(pack_bytes[:4], 16)
        if line_len == 0:
            break
        lines.append(pack_bytes[4:line_len])
        pack_bytes = pack_bytes[line_len:]
    pack_file = b"".join(l[1:] for l in lines[1:])
    
    # ">II" means big-endian unsigned int, unsigned int
    # https://docs.python.org/3/library/struct.html
    version_number, number_of_objects = struct.unpack(">II", pack_file[4:12])
    print(f"Version number: {version_number}", file=sys.stderr)
    print(f"Number of objects: {number_of_objects}", file=sys.stderr)
    
    objects = pack_file[12:]
    
    object_count = 0
    while objects:
        object_count += 1
        c = objects[0]
        obj_type = (c >> 4) & 7
        size = c & 15
        shift = 4
        i = 1

        while c & 0x80:  # Continue reading
            if shift > 32:
                size = 0
                break
            c = objects[i]
            i += 1
            size += (c & 0x7f) << shift
            shift += 7

        objects = objects[i:]

        print(f"{get_object_type_name(obj_type)} object, size: {size}")

        match obj_type:
            case ObjectType.COMMIT.value | ObjectType.TREE.value | ObjectType.BLOB.value | ObjectType.TAG.value:
                decompressed_data, objects = decompress_object(objects, size)
                write_object(dest_path, get_object_type_name(obj_type).encode(), decompressed_data)

            case ObjectType.REF_DELTA.value:
                base_obj_hash = objects[:20].hex()
                print(f"unpacking ref delta object {base_obj_hash}")
                objects = objects[20:]
                delta_data, objects = decompress_object(objects, size)
                base_obj_type, target_content = apply_ref_delta(base_obj_hash, delta_data, dest_path)

                write_object(dest_path, base_obj_type, target_content)

            case _:
                raise RuntimeError(f"Invalid object type")

        if object_count >= number_of_objects:
            print("All objects unpacked")
            break
            
    print(f"Unpacked {object_count} objects")
    _, commit = read_object(dest_path, refs["HEAD"])
    tree_sha = commit[5: 40 + 5].decode()
    build_tree(dest_path, dest_path, tree_sha)


def apply_ref_delta(base_obj_hash, delta_data, dest_path):
    target_content = b""
    base_obj_type, base_content = read_object(dest_path, base_obj_hash)
    src_size, pos = read_varint(delta_data, 0)
    tgt_size, pos = read_varint(delta_data, pos)
    delta_data = delta_data[pos:]
    while delta_data:
        opcode = delta_data[0]
        delta_data = delta_data[1:]
        if opcode & 0x80:  # Copy
            copy_offset = 0
            copy_length = 0
            if opcode & 0x01:
                copy_offset |= delta_data[0]
                delta_data = delta_data[1:]
            if opcode & 0x02:
                copy_offset |= delta_data[0] << 8
                delta_data = delta_data[1:]
            if opcode & 0x04:
                copy_offset |= delta_data[0] << 16
                delta_data = delta_data[1:]
            if opcode & 0x08:
                copy_offset |= delta_data[0] << 24
                delta_data = delta_data[1:]
            if opcode & 0x10:
                copy_length |= delta_data[0]
                delta_data = delta_data[1:]
            if opcode & 0x20:
                copy_length |= delta_data[0] << 8
                delta_data = delta_data[1:]
            if opcode & 0x40:
                copy_length |= delta_data[0] << 16
                delta_data = delta_data[1:]
            if copy_length == 0:
                copy_length = 0x10000
            target_content += base_content[copy_offset:copy_offset + copy_length]
        else:  # Insert
            insert_length = opcode
            target_content += delta_data[:insert_length]
            delta_data = delta_data[insert_length:]
    return base_obj_type, target_content


def write_tree():
    tree = hash_tree(os.getcwd())
    hashed = sha1(tree, usedforsecurity=False).hexdigest()
    print(hashed, end="")
    folder_path = f".git/objects/{hashed[:2]}"
    hashed_file_name = hashed[2:]
    os.makedirs(folder_path, exist_ok=True)
    with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
        hf.write(zlib.compress(tree))


def ls_tree(tree_hash: str, arg: str):
    tree_items = []
    with open(f".git/objects/{tree_hash[:2]}/{tree_hash[2:]}", "rb") as f:
        decompressed = zlib.decompress(f.read())
        head, data = decompressed.split(b"\0", maxsplit=1)
        if head[:4] == b"tree":
            while data:
                head, data = data.split(b"\0", maxsplit=1)
                mode, name = head.split(b" ", maxsplit=1)
                mode = int(mode)
                name = name.decode()
                item_hash = data[:20]
                tree_items.append(TreeEntry(mode, name, item_hash))

                data = data[20:]

        if arg == "--name-only":
            for item in tree_items:
                print(item.name)
        else:
            for item in tree_items:
                print(f"{item.mode} ", end="")
                if item.mode == Mode.DIRECTORY:
                    print("tree ", end="")
                else:
                    print("blob ", end="")
                print(f"{item.hash.hex()}\t{item.name}")


def read_object(path: Path, sha: str) -> (str, bytes):
    directory = sha[:2]
    file_name = sha[2:]
    p = path / ".git" / "objects" / directory / file_name
    data = p.read_bytes()
    head, content = zlib.decompress(data).split(b"\0", maxsplit=1)
    obj_type, _ = head.split(b" ")
    return obj_type, content


def write_object(path: Path, obj_type: bytes, content: bytes) -> str:
    content = obj_type + b" " + str(len(content)).encode() + b"\0" + content
    sha = sha1(content, usedforsecurity=False).hexdigest()
    print(f"write object {sha}")
    compressed_content = zlib.compress(content, level=zlib.Z_BEST_SPEED)
    directory = sha[:2]
    file_name = sha[2:]
    p = path / ".git" / "objects" / directory / file_name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(compressed_content)
    return sha

    
def get_object_type_name(obj_type: int) -> str:
    match obj_type:
        case ObjectType.COMMIT.value:
            return "commit"
        case ObjectType.TREE.value:
            return "tree"
        case ObjectType.BLOB.value:
            return "blob"
        case ObjectType.TAG.value:
            return "tag"
        case ObjectType.OFS_DELTA.value:
            return "ofs delta"
        case ObjectType.REF_DELTA.value:
            return "ref delta"
        case _:
            raise RuntimeError(f"Unknown object type {obj_type}")
    
    
    
def read_varint(data: bytes, pos: int) -> (int, int):
    """
    Reads a variable length integer from the data
    :param data: 
    :param pos: 
    :return: (result, position)
    """
    
    result: int = 0
    shift: int = 0
    while True:
        byte: int = data[pos]
        pos += 1
        result |= (byte & 0x7f) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result, pos


def commit_tree(commit_message: str, commit_sha: str, tree_sha: str):
    content = (
        f"tree {tree_sha}\n"
        f"parent {commit_sha}\n"
        f"author {GIT_AUTHOR_NAME} <{GIT_AUTHOR_EMAIL}> {int(time.time())} {time.timezone} "
        f"committer {GIT_AUTHOR_NAME} <{GIT_AUTHOR_EMAIL}> {int(time.time())} {time.timezone}\n\n"
        f"{commit_message}\n"
    )
    commit_object = f"commit {len(content)}\0{content}".encode()
    commit_hash = sha1(commit_object, usedforsecurity=False).hexdigest()
    folder_path = f".git/objects/{commit_hash[:2]}"
    hashed_file_name = commit_hash[2:]
    os.makedirs(folder_path, exist_ok=True)
    with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
        hf.write(zlib.compress(commit_object))
    print(commit_hash, end="")


def hash_tree(path: str, write: bool = True) -> bytes:
    dir_items = os.listdir(path)
    git_items = []
    for item in dir_items:
        if item == ".git":
            continue
        if os.path.isfile(os.path.join(path, item)):
            print(f"file {item}", file=sys.stderr)
            file_hash = hash_file(os.path.join(path, item), write)
            git_items.append(
                TreeEntry(
                    Mode.FILE,
                    item,
                    file_hash,
                )
            )
        elif os.path.isdir(os.path.join(path, item)):
            print(f"directory {item}", file=sys.stderr)
            tree = hash_tree(os.path.join(path, item))
            git_items.append(TreeEntry(Mode.DIRECTORY, item, sha1(tree, usedforsecurity=False).hexdigest()))

    git_items.sort(key=lambda i: i.name)

    tree_content = b""
    for item in git_items:
        tree_content += f"{str(item.mode)} {item.name}\0".encode()
        tree_content += int.to_bytes(int(item.hash, 16), length=20, byteorder="big")

    tree = f"tree {str(len(tree_content))}\0".encode() + tree_content

    return tree


def hash_file(path: str, write: bool = True) -> str:
    with open(path, "r") as f:
        file_content = f.read()
        to_be_hashed = f"blob {len(file_content)}\0{file_content}".encode()
        sha_hash = sha1(to_be_hashed, usedforsecurity=False).hexdigest()
        if write:
            folder_path = f".git/objects/{sha_hash[:2]}"
            hashed_file_name = sha_hash[2:]
            os.makedirs(folder_path, exist_ok=True)

            with open(f"{folder_path}/{hashed_file_name}", "wb") as hf:
                hf.write(zlib.compress(to_be_hashed))

        return sha_hash

        
def cat_file(object_hash: str):
    path = f".git/objects/{object_hash[:2]}/{object_hash[2:]}"
    with open(path, "rb") as f:
        decompressed = zlib.decompress(f.read())
        _, data = decompressed.split(b"\0", maxsplit=1)
        print(data.decode(), end="")


def init_repo(path: Path):
    os.makedirs(path, exist_ok=True)
    os.makedirs(path / ".git" / "objects", exist_ok=True)
    os.makedirs(path / ".git" / "refs", exist_ok=True)
    os.makedirs(path / ".git" / "refs" / "heads", exist_ok=True)
    with open(path / ".git" / "HEAD", "w") as f:
        f.write("ref: refs/heads/main\n")
    print(f"Initialized empty Git repository in {path}")
    

def extract_references(data: str) -> dict[str, str]:
    references: dict = {}
    lines = data.strip().split('\n')
    for line in lines:
        # Example line: 00327b8eb72b9dfa14a28ed22d7618b3cdecaa5d5be0 HEAD
        # The regex captures the SHA and the reference name
        # The first 4 characters are the length of the line
        # Then the SHA (40 characters), a space, and the reference name
        match = re.match(r'^[0-9a-f]{4}([0-9a-f]{40})\s+(.+)$', line)
        if match:
            sha, name = match.groups()
            references[name] = sha
    return references


def build_tree(path: Path, folder: Path, sha: str):
    folder.mkdir(parents=True, exist_ok=True)
    _, tree = read_object(path, sha)
    while tree:
        mode, tree = tree.split(b" ", maxsplit=1)
        name, tree = tree.split(b"\0", maxsplit=1)
        sha = tree[:20].hex()
        tree = tree[20:]
        match int(mode):
            case Mode.FILE.value:
                _, content = read_object(path, sha)
                with open(folder / name.decode(), "wb") as f:
                    f.write(content)
            case Mode.DIRECTORY.value:
                build_tree(path, folder / name.decode(), sha)
            case _:
                raise RuntimeError(f"unknown mode {mode}")

def decompress_object(data: bytes, expected_size: int) -> (bytes, bytes):
    decompressor = zlib.decompressobj()
    decompressed = decompressor.decompress(data, expected_size)
    decompressed += decompressor.flush()
    remainder = decompressor.unused_data
    
    assert decompressor.unconsumed_tail == b""
    assert len(decompressed) == expected_size
    
    return decompressed, remainder

if __name__ == "__main__":
    main()
