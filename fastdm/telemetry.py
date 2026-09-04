from __future__ import annotations

from PySide6.QtCore import QTimer


def install(main_window_cls) -> None:
    """Keep dashboard speed synchronized with the same task telemetry used by rows."""

    original_init = main_window_cls.__init__

    def _init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._speed_refresh_timer = QTimer(self)
        self._speed_refresh_timer.setInterval(250)
        self._speed_refresh_timer.timeout.connect(self._refresh_live_speed)
        self._speed_refresh_timer.start()
        self._refresh_live_speed()

    def _refresh_live_speed(self):
        active_speed = sum(
            max(0.0, float(task.speed))
            for task in self.tasks.values()
            if task.status == "downloading"
        )
        self.stat_speed.set_value(self._format_rate(active_speed))

        for task_id, row in self.rows.items():
            task = self.tasks.get(task_id)
            if not task:
                continue
            speed_item = self.table.item(row, 4)
            if speed_item:
                speed_item.setText(self._format_rate(task.speed if task.status == "downloading" else 0.0))

    main_window_cls.__init__ = _init
    main_window_cls._refresh_live_speed = _refresh_live_speed
