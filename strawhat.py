# -*- coding: utf-8 -*-
import zipfile
import os
import sys
import re

from lxml import etree
from StringIO import StringIO

class ProcessingError(Exception): pass
class NodeNotFound(ProcessingError):
    def __init__(self, node):
        self.node = node
class IncompleteAuthorInfo(ProcessingError): pass

def log(*args):
    log_entry = '  ' * log.indent + ' '.join(map(str, args)) + '\n'
    sys.stdout.write(log_entry)
    log_file.write(log_entry)
log.indent = 0

def normalize_filename(name):
    name = re.sub(r'[«»\"]', '\'', name)
    name = re.sub(r'(\.)+', r'\1', name)
    name = name.replace('?', '.')
    name = name.replace(':', ' -')
    name = name.replace(u'—', '-')
    name = name.replace(u'–', '-')
    name = re.sub(r'\s{2,}', ' ', name)
    return name.strip()

def normalize_author(name):
    return author_synonyms.get(name, name)

def process_book(file, name):
    def findall(selector, node=None, **kwargs):
        if node is None:
            node = tree
        xpath = etree.XPath(selector, namespaces={'fb2': 'http://www.gribuser.ru/xml/fictionbook/2.0'})
        result = xpath(node)
        if not len(result) and kwargs.get('required', True):
            raise NodeNotFound(selector)
        return result

    def find(selector, node=None, **kwargs):
        r = findall(selector, node, **kwargs)
        return r[0] if len(r) else None

    def get_text(node):
        if node is None or node.text is None or not len(node.text.strip()):
            return None
        return node.text

    tree = etree.parse(file)

    author = find('//fb2:title-info//fb2:author')
    first_name = find('//fb2:first-name', author, required=False)
    last_name = find('//fb2:last-name', author)

    if get_text(last_name) is None:
        raise IncompleteAuthorInfo()

    full_name = get_text(last_name).strip()
    if get_text(first_name) is not None:
        full_name += ', ' + get_text(first_name).strip()
    full_name = normalize_author(full_name)

    if u',' in full_name:
        last_name.text, first_name.text = [x.strip() for x in full_name.split(',', 2)]
    else:
        last_name.text = full_name

    title = find('//fb2:book-title').text

    sequence_text = u'Без серии'
    sequence = find('//fb2:title-info//fb2:sequence', required=False)
    if sequence is not None:
        if 'name' in sequence.attrib:
            new_sequence = sequence.attrib['name'].strip()
            if len(new_sequence):
                sequence_text = new_sequence
        if 'number' in sequence.attrib:
            try:
                title = u'%02d - %s' % (int(sequence.attrib['number']), title)
            except ValueError:
                pass

    path_parts = [library_dir, full_name, sequence_text, title + '.fb2']
    path_parts = map(normalize_filename, path_parts)

    full_path = os.path.join(*path_parts)
    filename = os.path.basename(full_path)
    path = os.path.dirname(full_path)
    if not os.path.exists(path):
        os.makedirs(path)

    #log("Create %s.zip" % (full_path))
    book = etree.tostring(tree, xml_declaration=True, pretty_print=True, encoding='utf-8')
    with zipfile.ZipFile(full_path + '.zip', 'w') as zip_file:
        zip_file.writestr(filename.encode('cp866'), book, zipfile.ZIP_DEFLATED)
    return True

def process_archive(file, name):
    success = True
    with zipfile.ZipFile(file) as zip_file:
        for name in zip_file.namelist():
            cur_file = StringIO(zip_file.read(name, 'r'))
            if not process_file(cur_file, os.path.basename(name)):
                success = False
            cur_file.close()
    return success

def process_file(file, name):
    log('Processing %s' % name)
    log.indent += 1
    success = False
    try:
        if name.endswith('.zip'):
            success = process_archive(file, name)
        elif name.endswith('.fb2'):
            success = process_book(file, name)
        else:
            success = True
            log('Unknown format - skipped')
    except IncompleteAuthorInfo:
        log("Error - incomplete author information")
    except NodeNotFound as e:
        log('Error - node "%s" not found' % (e.node))
    except ProcessingError:
        log('Error - processing failed')
    log.indent -= 1
    return success

if __name__ == '__main__':
    library_dir = 'books'
    income_dir = 'income'
    processed_dir = 'processed'
    authors_filename = 'authors.txt'
    log_filename = 'log.txt'

    log_file = open(log_filename, 'w')

    author_synonyms = {}
    if os.path.exists(authors_filename):
        with open(authors_filename, 'r') as authors_file:
            content = authors_file.read().decode('utf-8')
            for match in re.finditer('^(.*?)=(.*)$', content, re.MULTILINE):
                old_name = match.group(1).strip()
                new_name = match.group(2).strip()
                author_synonyms[old_name] = new_name

    for root, dirs, files in os.walk(income_dir):
        log('Processing directory "%s"' % (root))
        log.indent += 1
        for filename in files:
            archive = open(os.path.join(root, filename), 'rb')
            if process_file(archive, filename):
                new_root = processed_dir + root[len(income_dir):]
                if not os.path.exists(new_root):
                    os.makedirs(new_root)
                new_path = os.path.join(new_root, filename)
                if os.path.exists(new_path):
                    os.unlink(new_path)
                archive.close()
                os.rename(os.path.join(root, filename), new_path)
            else:
                archive.close()
        log.indent -= 1
    log_file.close()