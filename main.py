import sys
import aiohttp
import asyncio
import time
import os
import re
import webbrowser
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout, QSpacerItem, QSizePolicy, QMenu, QAction, QPushButton, QMessageBox, QProgressBar
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtGui import QPixmap
from datetime import datetime
import requests

class FetchGamesThread(QThread):
    finished = pyqtSignal(dict, float)

    def run(self):
        start_time = time.time()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.fetch_games(start_time))

    async def fetch_games(self, start_time):
        query = '''
        query Games {
          games {
            id
            locale
            title
            shortDescriptionPlainText
            springRollGame {
              created
              releases {
                url
                releaseUncompressedSize
                releaseCompressedSize
              }
            }
            mezzanine {
              ... on ImageAsset {
                id
                url
              }
            }
          }
        }
        '''
        url = 'https://graph.services.pbskids.org/'
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={'query': query}) as response:
                data = await response.json()
                elapsed_time = time.time() - start_time
                self.finished.emit(data, elapsed_time)

class AdvancedDetailsWindow(QWidget):
    def __init__(self, game_title, releases):
        super().__init__()
        self.setWindowTitle("Advanced Details")
        self.setGeometry(100, 100, 400, 300)
        self.game_title = game_title

        layout = QVBoxLayout()
        self.setLayout(layout)

        for release in releases:
            compressed_size = int(release['releaseCompressedSize'])
            uncompressed_size = int(release['releaseUncompressedSize'])
            compressed_size_hr = self.human_readable_size(compressed_size)
            uncompressed_size_hr = self.human_readable_size(uncompressed_size)

            details = f"Compressed Size: {compressed_size_hr}\n"
            details += f"Uncompressed Size: {uncompressed_size_hr}\n"

            details_label = QLabel(details)
            layout.addWidget(details_label)

            download_button = QPushButton("Download")
            download_button.clicked.connect(lambda _, url=release['url']: self.download_game(url))
            layout.addWidget(download_button)

    def human_readable_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    def download_game(self, url):
        sanitized_title = self.sanitize_filename(self.game_title)
        if isinstance(url, str):
            zip_url = url.replace('/index.html', '.zip')
            file_name = f"{sanitized_title}.zip"
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads", file_name)

            self.start_download(zip_url, downloads_path)
        else:
            QMessageBox.warning(self, "Download Error", "Invalid URL")

    def sanitize_filename(self, filename):
        sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
        sanitized = re.sub(r'\s+', '_', sanitized)
        return sanitized

    def start_download(self, zip_url, file_path):
        self.download_window = DownloadProgressWindow(zip_url, file_path)
        self.download_window.show()

class DownloadProgressWindow(QWidget):
    def __init__(self, zip_url, file_path):
        super().__init__()
        self.setWindowTitle("Downloading")
        self.setGeometry(100, 100, 300, 100)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Starting download...")
        layout.addWidget(self.status_label)

        self.zip_url = zip_url
        self.file_path = file_path

        self.download_file()

    def download_file(self):
        self.thread = DownloadThread(self.zip_url, self.file_path)
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.on_download_finished)
        self.thread.start()

    def update_progress(self, progress):
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"Downloading: {progress}%")

    def on_download_finished(self, success):
        if success:
            self.status_label.setText("Download complete!")
        else:
            self.status_label.setText("Download failed.")
        self.progress_bar.setValue(100)

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool)

    def __init__(self, zip_url, file_path):
        super().__init__()
        self.zip_url = zip_url
        self.file_path = file_path

    def run(self):
        try:
            response = requests.get(self.zip_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(self.file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
                    downloaded_size += len(chunk)
                    progress = int(100 * downloaded_size / total_size)
                    self.progress.emit(progress)

            self.finished.emit(True)
        except Exception:
            self.finished.emit(False)

class GamesApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("PBS Kids Games")
        self.setGeometry(100, 100, 800, 600)

        self.layout = QVBoxLayout(self)

        self.stats_label = QLabel("Fetching data...")
        self.layout.addWidget(self.stats_label)

        self.scrollArea = QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaContent = QWidget()
        self.scrollAreaLayout = QVBoxLayout(self.scrollAreaContent)
        self.scrollArea.setWidget(self.scrollAreaContent)

        self.layout.addWidget(self.scrollArea)

        self.fetchGames()

    def fetchGames(self):
        self.thread = FetchGamesThread()
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, data, elapsed_time):
        games = data.get('data', {}).get('games', [])
        self.stats_label.setText(f"Retrieved {len(games)} games in {elapsed_time:.2f} seconds")
        self.display_games(games)

    def display_games(self, games):
        for i in reversed(range(self.scrollAreaLayout.count())):
            widget = self.scrollAreaLayout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        def get_created_date(game):
            spring_roll_game = game.get('springRollGame')
            if spring_roll_game and 'created' in spring_roll_game:
                return spring_roll_game['created']
            return ''

        games_sorted = sorted(games, key=get_created_date, reverse=True)

        for game in games_sorted:
            game_frame = QFrame()
            game_frame.setStyleSheet("""
                QFrame {
                    padding: 10px;
                    border-radius: 5px;
                    background-color: white;
                }
                QFrame:hover {
                    background-color: rgba(0, 0, 255, 0.2);
                }
            """)
            game_frame.setContextMenuPolicy(Qt.CustomContextMenu)
            game_frame.customContextMenuRequested.connect(lambda pos, f=game_frame, g=game: self.show_context_menu(pos, f, g))
            game_frame.mouseDoubleClickEvent = lambda event, g=game: self.open_release_url(g)

            game_layout = QHBoxLayout()

            image_label = QLabel()
            if game.get('mezzanine'):
                image_url = game['mezzanine'][0]['url']
                self.load_image(image_label, image_url)
            game_layout.addWidget(image_label)

            details_layout = QVBoxLayout()
            title_label = QLabel(f"<b>{game['title']}</b>")
            details_layout.addWidget(title_label)
            description_label = QLabel(game['shortDescriptionPlainText'])
            description_label.setWordWrap(True)
            details_layout.addWidget(description_label)

            spring_roll_game = game.get('springRollGame')
            if spring_roll_game and 'created' in spring_roll_game:
                release_date = self.human_readable_date(spring_roll_game['created'])
            else:
                release_date = "Unknown"

            release_label = QLabel(f"Release Date: {release_date}")
            details_layout.addWidget(release_label)
            details_layout.addStretch()

            game_layout.addLayout(details_layout)
            game_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
            game_frame.setLayout(game_layout)
            game_frame.setFrameShape(QFrame.StyledPanel)

            self.scrollAreaLayout.addWidget(game_frame)

        self.scrollAreaLayout.addStretch()

    def load_image(self, image_label, url):
        manager = QNetworkAccessManager(self)
        manager.finished.connect(lambda reply: self.on_image_loaded(reply, image_label))
        request = QNetworkRequest(QUrl(url))
        manager.get(request)

    def on_image_loaded(self, reply, image_label):
        if reply.error() == QNetworkReply.NoError:
            image = QPixmap()
            image.loadFromData(reply.readAll())
            image_label.setPixmap(image.scaledToWidth(200, Qt.SmoothTransformation))
        reply.deleteLater()

    def human_readable_date(self, iso_date):
        try:
            date_obj = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            return date_obj.strftime("%b %d, %Y")
        except ValueError:
            return iso_date

    def show_context_menu(self, pos, frame, game):
        menu = QMenu(self)
        action_advanced_details = QAction('Advanced Details', self)
        action_advanced_details.triggered.connect(lambda: self.open_advanced_details(game))
        menu.addAction(action_advanced_details)

        menu.exec_(frame.mapToGlobal(pos))

    def open_advanced_details(self, game):
        releases = game.get('springRollGame', {}).get('releases', [])
        self.advanced_details_window = AdvancedDetailsWindow(game['title'], releases)
        self.advanced_details_window.show()

    def open_release_url(self, game):
        releases = game.get('springRollGame', {}).get('releases', [])
        if releases:
            webbrowser.open(releases[0]['url'])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GamesApp()
    ex.show()
    sys.exit(app.exec_())
