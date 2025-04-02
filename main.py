import os
import re
import json
import threading
import concurrent.futures
from pathlib import Path
import time
import colorama
from colorama import Fore, Style, Back

colorama.init(autoreset=True)

class FileSearcher:
    def __init__(self, search_term, directory, exclude_patterns=None, max_workers=1000, 
                 file_extensions=None, case_sensitive=False):
        self.search_term = search_term
        self.directory = directory
        self.exclude_patterns = exclude_patterns or []
        self.max_workers = max(1, max_workers)
        self.file_extensions = file_extensions or ['.txt', '.json', '.sql', '.py', '.md', '.csv', '.log', '.xml', '.html', '.js', '.css']
        self.case_sensitive = case_sensitive
        self.results = {}
        self.files_processed = 0
        self.matches_found = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
    
    def is_excluded(self, file_path):
        return any(re.search(pattern, file_path) for pattern in self.exclude_patterns)
    
    def is_binary_file(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                return b'\0' in f.read(1024)
        except Exception:
            return True
    
    def is_searchable_file(self, file_path):
        if self.is_excluded(file_path) or self.is_binary_file(file_path):
            return False
        ext = os.path.splitext(file_path)[1].lower()
        return not self.file_extensions or ext in self.file_extensions
    
    def search_file(self, file_path):
        matches = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if (self.case_sensitive and self.search_term in line) or \
                       (not self.case_sensitive and self.search_term.lower() in line.lower()):
                        matches.append({
                            'line_num': line_num,
                            'line': line.rstrip(),
                            'file_path': file_path
                        })
            
            if file_path.lower().endswith('.json'):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        json_data = json.load(f)
                    matches.extend(self.search_json(json_data, file_path))
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"{Fore.RED}Error processing {file_path}: {str(e)}")
        return matches
    
    def search_json(self, data, file_path, path="$"):
        matches = []
        if isinstance(data, dict):
            for k, v in data.items():
                current_path = f"{path}.{k}"
                if (self.case_sensitive and self.search_term in str(k)) or \
                   (not self.case_sensitive and self.search_term.lower() in str(k).lower()):
                    matches.append({
                        'line_num': 0,
                        'line': f"{current_path}: {str(k)}",
                        'file_path': file_path,
                        'json_path': current_path
                    })
                if isinstance(v, (dict, list)):
                    matches.extend(self.search_json(v, file_path, current_path))
                elif isinstance(v, str) and ((self.case_sensitive and self.search_term in v) or 
                                            (not self.case_sensitive and self.search_term.lower() in v.lower())):
                    matches.append({
                        'line_num': 0,
                        'line': f"{current_path}: {v}",
                        'file_path': file_path,
                        'json_path': current_path
                    })
                elif self.search_term in str(v):
                    matches.append({
                        'line_num': 0,
                        'line': f"{current_path}: {str(v)}",
                        'file_path': file_path,
                        'json_path': current_path
                    })
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    matches.extend(self.search_json(item, file_path, current_path))
                elif isinstance(item, str) and ((self.case_sensitive and self.search_term in item) or 
                                              (not self.case_sensitive and self.search_term.lower() in item.lower())):
                    matches.append({
                        'line_num': 0,
                        'line': f"{current_path}: {item}",
                        'file_path': file_path,
                        'json_path': current_path
                    })
                elif self.search_term in str(item):
                    matches.append({
                        'line_num': 0,
                        'line': f"{current_path}: {str(item)}",
                        'file_path': file_path,
                        'json_path': current_path
                    })
        return matches
    
    def process_file(self, file_path):
        if not self.is_searchable_file(file_path):
            return
        matches = self.search_file(file_path)
        if matches:
            with self.lock:
                self.results[file_path] = matches
                self.matches_found += len(matches)
        with self.lock:
            self.files_processed += 1
            
    def search_directory(self):
        all_files = []
        for root, _, files in os.walk(self.directory):
            for file in files:
                all_files.append(os.path.join(root, file))
        
        total_files = len(all_files)
        if total_files == 0:
            print(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT} No files found to search in {self.directory} {Style.RESET_ALL}")
            return self.results
            
        print(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT} Found {total_files} files to search {Style.RESET_ALL}")
        effective_workers = max(1, min(self.max_workers, total_files))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = [executor.submit(self.process_file, file_path) for file_path in all_files]
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                if i % 100 == 0 or i == total_files - 1:
                    progress = (i + 1) / total_files * 100
                    elapsed = time.time() - self.start_time
                    files_per_sec = (i + 1) / elapsed if elapsed > 0 else 0
                    print(f"{Fore.RED}{Style.BRIGHT}Progress: {progress:.1f}% ({i+1}/{total_files}) - {files_per_sec:.1f} files/sec{Style.RESET_ALL}", end='\r')
        
        print(f"\n{Back.RED}{Fore.WHITE}{Style.BRIGHT} Search completed. Processed {self.files_processed} files and found {self.matches_found} matches. {Style.RESET_ALL}")
        return self.results
    
    def print_results(self):
        if not self.results:
            print(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT} No matches found for '{self.search_term}' {Style.RESET_ALL}")
            return
            
        print(f"\n{Back.RED}{Fore.WHITE}{Style.BRIGHT} Search Results for '{self.search_term}' {Style.RESET_ALL}")
        print(f"{Fore.RED}{Style.BRIGHT}{'=' * 80}{Style.RESET_ALL}")
        
        for file_path, matches in self.results.items():
            rel_path = os.path.relpath(file_path, self.directory)
            print(f"\n{Back.RED}{Fore.WHITE}{Style.BRIGHT} File: {rel_path} ({len(matches)} matches) {Style.RESET_ALL}")
            
            for match in matches:
                if 'json_path' in match:
                    print(f"{Fore.RED}{Style.BRIGHT}JSON Path: {match['json_path']}{Style.RESET_ALL}")
                    highlighted_line = self.highlight_match(match['line'])
                    print(f"  {highlighted_line}")
                else:
                    line_num = match['line_num']
                    print(f"{Fore.RED}{Style.BRIGHT}Line {line_num}:{Style.RESET_ALL}")
                    highlighted_line = self.highlight_match(match['line'])
                    print(f"  {highlighted_line}")
                    
        print(f"\n{Back.RED}{Fore.WHITE}{Style.BRIGHT} Total: {self.matches_found} matches in {len(self.results)} files {Style.RESET_ALL}")
        print(f"{Fore.RED}{Style.BRIGHT}Time taken: {time.time() - self.start_time:.2f} seconds{Style.RESET_ALL}")
    
    def highlight_match(self, line):
        pattern = re.escape(self.search_term)
        if self.case_sensitive:
            return re.sub(f'({pattern})', f'{Back.RED}{Fore.WHITE}{Style.BRIGHT}\\1{Style.RESET_ALL}', line)
        else:
            return re.sub(f'({pattern})', f'{Back.RED}{Fore.WHITE}{Style.BRIGHT}\\1{Style.RESET_ALL}', line, flags=re.IGNORECASE)

def interactive_cli():
    print(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}                        DB SEARCHER - The FASTEST SEARCHER in the world                         {Style.RESET_ALL}")
    print(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}                        Made by NightKikko https://github.com/NightKikko                        {Style.RESET_ALL}")
    print(f"{Fore.RED}{Style.BRIGHT}{'=' * 80}{Style.RESET_ALL}")
    
    search_term = input(f"{Back.RED}{Fore.WHITE} Enter search term: {Style.RESET_ALL} ")
    
    directory = input(f"{Back.RED}{Fore.WHITE} Enter directory to search [.]: {Style.RESET_ALL} ")
    directory = directory.strip() or '.'
    
    exclude_input = input(f"{Back.RED}{Fore.WHITE} Enter patterns to exclude (comma separated) [node_modules,.git,venv]: {Style.RESET_ALL} ")
    exclude_patterns = [p.strip() for p in exclude_input.split(',')] if exclude_input.strip() else ['node_modules', '.git', 'venv']
    
    extensions_input = input(f"{Back.RED}{Fore.WHITE} Enter file extensions to search (comma separated, leave empty for all common text files): {Style.RESET_ALL} ")
    file_extensions = [f".{ext.strip().lstrip('.')}" for ext in extensions_input.split(',')] if extensions_input.strip() else None
    
    threads_input = input(f"{Back.RED}{Fore.WHITE} Enter maximum number of threads [1000]: {Style.RESET_ALL} ")
    max_workers = int(threads_input) if threads_input.strip() and threads_input.strip().isdigit() else 1000
    max_workers = max(1, max_workers)
    
    case_sensitive_input = input(f"{Back.RED}{Fore.WHITE} Case sensitive search? (y/n) [n]: {Style.RESET_ALL} ")
    case_sensitive = case_sensitive_input.lower().startswith('y')
    
    print(f"\n{Back.RED}{Fore.WHITE}{Style.BRIGHT} SEARCH PARAMETERS {Style.RESET_ALL}")
    print(f"{Fore.RED}{Style.BRIGHT}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.RED}Search term: {Fore.WHITE}{search_term}")
    print(f"{Fore.RED}Directory: {Fore.WHITE}{directory}")
    print(f"{Fore.RED}Exclude patterns: {Fore.WHITE}{exclude_patterns}")
    print(f"{Fore.RED}File extensions: {Fore.WHITE}{file_extensions or 'All common text files'}")
    print(f"{Fore.RED}Max threads: {Fore.WHITE}{max_workers}")
    print(f"{Fore.RED}Case sensitive: {Fore.WHITE}{case_sensitive}")
    print(f"{Fore.RED}{Style.BRIGHT}{'=' * 80}{Style.RESET_ALL}\n")
    
    searcher = FileSearcher(
        search_term=search_term,
        directory=directory,
        exclude_patterns=exclude_patterns,
        max_workers=max_workers,
        file_extensions=file_extensions,
        case_sensitive=case_sensitive
    )
    
    searcher.search_directory()
    searcher.print_results()

if __name__ == "__main__":
    interactive_cli()