# -*- coding: utf-8 -*-
import os
import json
import time
import uuid
import threading
import xbmc
import xbmcgui
import xbmcaddon
from lib.network import rqs_get
from lib.constants import WNT2_USER_AGENT, BASEURL
from lib.common import translate_path

PROP_DOWNLOADS = 'wnt2_downloads_list'

class DownloadManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def getInstance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = DownloadManager()
        return cls._instance

    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.profile = translate_path(self.addon.getAddonInfo('profile'))
        if not os.path.exists(self.profile):
            os.makedirs(self.profile)
        self.filepath = os.path.join(self.profile, 'downloads.json')
        self.tasks = self._load_tasks()
        self.active_thread = None
        self.stop_flag = False

    def _load_tasks(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_tasks(self):
        with self._lock:
            with open(self.filepath, 'w') as f:
                json.dump(self.tasks, f)

    def get_tasks(self):
        return self.tasks

    def add_task(self, name, folder, page_url=None, stream_url=None):
        task_data = {
            'id': str(uuid.uuid4()),
            'name': name,
            'folder': folder,
            'page_url': page_url,
            'stream_url': stream_url,
            'status': 'pending',
            'progress': 0,
            'filepath': '',
            'error': ''
        }
        self.tasks.append(task_data)
        self._save_tasks()
        xbmcgui.Dialog().notification('Download Added', name, xbmcgui.NOTIFICATION_INFO)

    def start(self, resolve_func=None):
        if self.active_thread and self.active_thread.is_alive():
            return
        self.stop_flag = False
        self.active_thread = threading.Thread(target=self._worker, args=(resolve_func,))
        self.active_thread.start()
        xbmcgui.Dialog().notification('Download Manager', 'Queue Started', xbmcgui.NOTIFICATION_INFO)

    def stop(self):
        self.stop_flag = True

    def _worker(self, resolve_func):
        while not self.stop_flag:
            task = next((t for t in self.tasks if t['status'] == 'pending'), None)
            if not task:
                break
            self._process_task(task, resolve_func)

    def _process_task(self, task, resolve_func):
        try:
            stream_url = task.get('stream_url')
            if not stream_url and task.get('page_url'):
                if resolve_func:
                    task['status'] = 'resolving'
                    self._save_tasks()
                    stream_url = resolve_func(task['page_url'])
                    if not stream_url:
                        raise Exception('Failed to resolve URL')
                    task['stream_url'] = stream_url
                else:
                    raise Exception('No resolver provided')

            task['status'] = 'downloading'
            self._save_tasks()
            
            self._download_file(task, stream_url)
            
            # Check if cancelled during download
            current_task = next((t for t in self.tasks if t['id'] == task['id']), None)
            if current_task and current_task['status'] == 'downloading':
                current_task['status'] = 'completed'
                current_task['progress'] = 100
                self._save_tasks()
                xbmcgui.Dialog().notification('Download Completed', task['name'], xbmcgui.NOTIFICATION_INFO)

        except Exception as e:
            task['status'] = 'error'
            task['error'] = str(e)
            self._save_tasks()
            xbmcgui.Dialog().notification('Download Error', str(e), xbmcgui.NOTIFICATION_ERROR)

    def _download_file(self, task, url):
        headers = {
            'User-Agent': WNT2_USER_AGENT,
            'Referer': BASEURL + '/',
        }
        
        response = rqs_get().get(url, stream=True, headers=headers, verify=False, timeout=30)
        if not response.ok:
            raise Exception('HTTP ' + str(response.status_code))

        # Determine file extension
        content_type = response.headers.get('Content-Type', 'video/mp4').lower()
        if 'mp4' in content_type: file_ext = '.mp4'
        elif 'webm' in content_type: file_ext = '.webm'
        elif 'ogg' in content_type or 'ogv' in content_type: file_ext = '.ogv'
        elif 'quicktime' in content_type: file_ext = '.mov'
        else: file_ext = '.mp4'

        filename = task['name']
        if not filename.endswith(file_ext):
            filename += file_ext
            
        filepath = os.path.join(task['folder'], filename)
        task['filepath'] = filepath
        self._save_tasks()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        last_update = 0
        chunk_count = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if self.stop_flag:
                    raise Exception('Stopped by user')

                chunk_count += 1
                if chunk_count % 20 == 0:
                    current_task = next((t for t in self.tasks if t['id'] == task['id']), None)
                    if not current_task or current_task.get('status') == 'cancelling':
                        f.close()
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        if current_task:
                            current_task['status'] = 'cancelled'
                            self._save_tasks()
                        return

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        if percent > last_update:
                            task['progress'] = percent
                            self._save_tasks()
                            last_update = percent

    def cancel(self, task_id):
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if task:
            if task['status'] == 'downloading':
                task['status'] = 'cancelling'
            elif task['status'] == 'pending':
                task['status'] = 'cancelled'
            self._save_tasks()

    def remove(self, task_id):
        self.cancel(task_id)
        self.tasks = [t for t in self.tasks if t['id'] != task_id]
        self._save_tasks()