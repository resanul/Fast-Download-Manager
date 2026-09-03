from __future__ import annotations
import sys, uuid
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QFileDialog
from .engine import DownloadEngine, DownloadTask

class Worker(QObject):
    progress=Signal(object); finished=Signal(object); failed=Signal(str)
    def __init__(self, engine, task): super().__init__(); self.engine=engine; self.task=task
    @Slot()
    def run(self):
        import asyncio
        try: self.finished.emit(asyncio.run(self.engine.download(self.task, self.progress.emit)))
        except Exception as e: self.failed.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Fast Download Manager'); self.resize(1100,700); self.engine=DownloadEngine(); self.rows={}
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        title=QLabel('Fast Download Manager'); title.setObjectName('title'); layout.addWidget(title)
        bar=QHBoxLayout(); self.url=QLineEdit(); self.url.setPlaceholderText('Paste a download URL…'); bar.addWidget(self.url,1); b=QPushButton('+ Add Download'); b.clicked.connect(self.add_download); bar.addWidget(b); layout.addLayout(bar)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(['File','Status','Progress','Speed','Size']); layout.addWidget(self.table)
        self.status=QLabel('Ready'); layout.addWidget(self.status)
        self.setStyleSheet('QMainWindow{background:#101318;color:#eee} QLabel#title{font-size:28px;font-weight:700;margin:12px} QLineEdit,QTableWidget{background:#181c23;color:#eee;border:1px solid #303744;border-radius:8px;padding:8px} QPushButton{background:#2563eb;color:white;border:0;border-radius:8px;padding:10px 16px;font-weight:600} QHeaderView::section{background:#222733;color:#bbb;padding:8px}')
    def add_download(self):
        url=self.url.text().strip()
        if not url: return
        folder=QFileDialog.getExistingDirectory(self,'Choose download folder')
        if not folder: return
        name=Path(url.split('?',1)[0]).name or 'download'; task=DownloadTask(uuid.uuid4().hex,url,Path(folder)/name); row=self.table.rowCount(); self.table.insertRow(row); self.rows[task.id]=row
        for c,v in enumerate([name,'starting','0%','0 B/s','Unknown']): self.table.setItem(row,c,QTableWidgetItem(v))
        self.url.clear(); thread=QThread(); worker=Worker(self.engine,task); worker.moveToThread(thread); thread.started.connect(worker.run); worker.progress.connect(self.progress); worker.finished.connect(self.done); worker.failed.connect(self.fail); worker.finished.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater); self.threads=getattr(self,'threads',[]); self.threads.append(thread); thread.start()
    def progress(self,t):
        r=self.rows[t.id]; total=t.total or 0; pct=t.downloaded*100/total if total else 0; self.table.item(r,1).setText(t.status); self.table.item(r,2).setText(f'{pct:.1f}%'); self.table.item(r,3).setText(f'{t.speed/1048576:.2f} MB/s'); self.table.item(r,4).setText(self.fmt(total))
    def done(self,t): self.progress(t); self.table.item(self.rows[t.id],1).setText('completed'); self.status.setText('Download completed')
    def fail(self,e): self.status.setText('Download failed: '+e)
    @staticmethod
    def fmt(n):
        if not n:return 'Unknown'
        for u in ('B','KB','MB','GB','TB'):
            if n<1024:return f'{n:.1f} {u}'
            n/=1024
        return f'{n:.1f} PB'
    def closeEvent(self,e): self.engine.shutdown(); e.accept()

def main():
    app=QApplication(sys.argv); w=MainWindow(); w.show(); return app.exec()
