import flet as ft
import requests
import threading
import time
import os


# URL backendu z ustawień środowiskowych lub domyślnie localhost
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class BackendMonitor:
    # klasa która sprawdza czy backend działa - co chwilę wysyła zapytanie /health

    def __init__(self, app_ref):
        self.app_ref = app_ref  # referencja do głównej aplikacji żeby aktualizować UI
        self.is_online = False  # czy backend jest online
        self.monitoring = False  # czy monitorowanie jest aktywne
        self.retry_count = 0  # ile razy próbowalem sie poolaczyc

    def start_monitoring(self):
        # uruchamiamy osobny wątek sprawdzajacy backend
        if not self.monitoring:
            self.monitoring = True
            threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        # pętla która co chwilę sprawdza backend 
        while self.monitoring:
            was_online = self.is_online
            self.check_backend_health()
            # jeśli cos wywalilo, a teraz jest połączenie
            if not was_online and self.is_online:
                self.app_ref.on_backend_reconnected()  # powiadamiamy appkę
                self.retry_count = 0  # resetujemy licznik prób
            # czas czekania między próbami zależny od stanu (backoff)
            sleep_time = 5 if self.is_online else min(2 ** self.retry_count, 30)
            if not self.is_online:
                self.retry_count += 1
            time.sleep(sleep_time)

    def check_backend_health(self):
        # endpoint health
        try:
            response = requests.get(f"{BACKEND_URL}/health", timeout=3)
            if response.status_code == 200:
                self.is_online = True
                # aktualizujemy status jak polaczylo
                self.app_ref.update_connection_status("Connected ✓", ft.Colors.GREEN)
            else:
                raise Exception("Health check failed")
        except:
            self.is_online = False
            # brak polaczenia i ile prób połaczenia
            # to do można dodać więcej logiki np. zliczanie błędów
            status = f"Backend offline (Retry {self.retry_count})" if self.retry_count > 0 else "Backend offline"
            self.app_ref.update_connection_status(status, ft.Colors.RED)

    def manual_retry(self):
        # ręczna próba połączenia np. kliknięcie przycisku "Retry"
        # to do - można dodać logikę by nie spamować próbami np co 5 sekund?
        # to do - niech wyświetla status ile razy próbowano się połączyć nadal mimo wciśnięcia retry
        self.retry_count = 0
        self.app_ref.update_connection_status("Connecting...", ft.Colors.ORANGE)
        threading.Thread(target=self.check_backend_health, daemon=True).start()


class ApiClient:
    # API HTTP do backendu (GET, POST, PUT, DELETE)

    @staticmethod
    def make_request(method: str, url: str, json_data=None, timeout=5):
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, json=json_data, timeout=timeout)
            elif method.upper() == "PUT":
                response = requests.put(url, json=json_data, timeout=timeout)
            elif method.upper() == "DELETE":
                response = requests.delete(url, timeout=timeout)
            else:
                return None, "Unsupported method"
            response.raise_for_status()
            return response.json() if response.content else {}, None
        except Exception as e:
            return None, str(e)


class Task(ft.Column):
    # pojedyncze zadanie z checkboxem, edycją i usuwaniem

    def __init__(self, task_name, task_status_change, task_delete, id=None, app_ref=None):
        super().__init__()
        self.id = id  # id zadania w bazie backendu
        self.completed = False  # czy zadanie jest wykonane
        self.task_name = task_name
        self.task_status_change = task_status_change  # callback przy zmianie statusu
        self.task_delete = task_delete  # callback przy usuwaniu
        self.app_ref = app_ref  # referencja do aplikacji

        # widok zadania - checkbox z nazwą i przyciski edycji oraz usuwania
        self.display_task = ft.Checkbox(
            value=False, label=self.task_name, on_change=self.status_changed
        )
        self.edit_name = ft.TextField(expand=1)  # pole do edycji nazwy zadania

        # widok standardowy (lista zadań)
        self.display_view = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.display_task,
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.CREATE_OUTLINED,
                            tooltip="Edit To-Do",
                            on_click=self.edit_clicked,
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Delete To-Do",
                            on_click=self.delete_clicked,
                        ),
                    ],
                ),
            ],
        )

        # widok edycyjny (pole tekstowe + przycisk zatwierdzenia)
        self.edit_view = ft.Row(
            visible=False,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.edit_name,
                ft.IconButton(
                    icon=ft.Icons.DONE_OUTLINE_OUTLINED,
                    icon_color=ft.Colors.GREEN,
                    tooltip="Update To-Do",
                    on_click=self.save_clicked,
                ),
            ],
        )

        self.controls = [self.display_view, self.edit_view]

    def edit_clicked(self, e):
        # kliknięcie "edytuj" - pokaż pole edycji i ukryj listę
        self.edit_name.value = self.display_task.label
        self.display_view.visible = False
        self.edit_view.visible = True
        self.update()

    def save_clicked(self, e):
        # zapisz zmiany nazwy i zaktualizuj backend
        new_title = self.edit_name.value.strip()
        if not new_title:
            return  # bez pustej nazwy
        old_title = self.display_task.label
        self.display_task.label = new_title
        self.display_view.visible = True
        self.edit_view.visible = False
        self.update()

        # jeśli zadanie ma id to aktualizujemy
        if self.id is not None:
            def update_backend():
                data, error = ApiClient.make_request(
                    "PUT", f"{BACKEND_URL}/todos/{self.id}",
                    {"title": new_title, "completed": self.completed}
                )
                #  jak wywala błąd to cofamy 
                if error:
                    self.display_task.label = old_title
                    self.update()

            threading.Thread(target=update_backend, daemon=True).start()

    def status_changed(self, e):
        # zmiana checkboxa - zmieniamy completed i do backendu
        old_completed = self.completed
        self.completed = self.display_task.value

        if self.id is not None:
            def update_status():
                data, error = ApiClient.make_request(
                    "PUT", f"{BACKEND_URL}/todos/{self.id}",
                    {"title": self.display_task.label, "completed": self.completed}
                )
                # jeśli błąd cofamy as always
                
                if error:
                    self.completed = old_completed
                    self.display_task.value = old_completed
                    self.update()

            threading.Thread(target=update_status, daemon=True).start()

        self.task_status_change(self)  # callback do odswieżenia UI

    def delete_clicked(self, e):
        # kliknięcie usuń - usuwamy z UI i z  backendu jeśli mamy id taska
        self.task_delete(self)
        if self.id is not None:
            def delete_backend():
                ApiClient.make_request("DELETE", f"{BACKEND_URL}/todos/{self.id}")

            threading.Thread(target=delete_backend, daemon=True).start()


class TodoApp(ft.Column):
    # główna aplikacja 

    def __init__(self, page):
        super().__init__()
        self.page = page

        # monitorujemy backend czy jest online/offline
        self.backend_monitor = BackendMonitor(self)

        # wyświetlamy status połączenia
        self.connection_status = ft.Text(
            "Checking backend...",
            color=ft.Colors.ORANGE,
            size=12
        )

        # retry connection button 
        self.retry_button = ft.ElevatedButton(
            "Retry",
            icon=ft.Icons.REFRESH,
            on_click=self.manual_retry,
            height=30,
            visible=False
        )

        # dodawanie nowych zadań
        self.new_task = ft.TextField(
            hint_text="What do we have to do today?",
            on_submit=self.add_clicked,
            expand=True,
            border_color=ft.Colors.BLUE_400,
            focused_border_color=ft.Colors.BLUE_400,
        )

        # dodaj zadanie ( enter również działa, )
        self.add_button = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=self.add_clicked,
        )

        # miejsce na listę zadań
        self.tasks = ft.Column()

        # zakładki wg statusu filtr
        self.filter = ft.Tabs(
            scrollable=False,
            selected_index=0,
            on_change=self.tabs_changed,
            tabs=[
                ft.Tab(text="Active To-Dos"),
                ft.Tab(text="All To-dos"),
                ft.Tab(text="Completed To-Dos"),
            ],
        )

        # info ile zadań zostało
        self.items_left = ft.Text("0 items left")

        self.width = 600

        # dodajemy elementy do głównego layoutu
        self.controls = [
            # status i retry przy jednej linii centrowanej
            ft.Row([
                self.connection_status,
                self.retry_button
            ], alignment=ft.MainAxisAlignment.CENTER),

            # nagłówek aplikacji
            ft.Row(
                [
                    ft.Text(
                        value="To Do!",
                        theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            # pole plus przycisk dodawania
            ft.Row(
                controls=[
                    self.new_task,
                    self.add_button,
                ],
            ),

            # zakładki z listą i przyciskiem kasowania wykonanych tasków
            ft.Column(
                spacing=25,
                controls=[
                    self.filter,
                    self.tasks,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.items_left,
                            ft.OutlinedButton(
                                text="Clear completed",
                                on_click=self.clear_clicked,
                            ),
                        ],
                    ),
                ],
            ),
        ]

        # startujemy monitorowanie backendu i ładujemy listę zadań
        self.backend_monitor.start_monitoring()
        self.load_todos_from_backend()

    def manual_retry(self, e):
        # kliknięcie retry 
        self.backend_monitor.manual_retry()

    def on_backend_reconnected(self):
        # gdy backend teraz jest online, to ładujemy zadania
        self.load_todos_from_backend()

    def update_connection_status(self, status: str, color):
        # aktualizuj tekst i kolor statusu połączenia
        self.connection_status.value = status
        self.connection_status.color = color
        # pokaż przycisk retry tylko jak backend offline 
        self.retry_button.visible = color == ft.Colors.RED
        if self.page:
            self.page.update()

    def load_todos_from_backend(self):
        # ładowanie zadań z backendu asynchronicznie

        def load_async():
            data, error = ApiClient.make_request("GET", f"{BACKEND_URL}/todos")
            # jeśli pomyślnie pobraliśmy dane to czyścimy listę i ładujemy od nowa
            if not error:
                self.tasks.controls.clear()
                for todo in data:
                    task = Task(
                        todo["title"],
                        self.task_status_change,
                        self.task_delete,
                        id=todo["id"],
                        app_ref=self
                    )
                    task.completed = todo.get("completed", False)
                    task.display_task.value = task.completed
                    self.tasks.controls.append(task)
                if self.page:
                    self.update()
            else:
                # jeśli błąd to nie czyścimy listy, tylko wypisujemy błąd do konsoli
                print(f"Error loading todos from backend: {error}")

        threading.Thread(target=load_async, daemon=True).start()

    def add_clicked(self, e):
        # dodawanie nowego zadania

        if not self.new_task.value or not self.new_task.value.strip():
            return  # ignorujemy puste

        new_title = self.new_task.value.strip()

        # dodajemy tymczasowe zadanie od razu do listy UI
        temp_task = Task(
            new_title,
            self.task_status_change,
            self.task_delete,
            id=None,
            app_ref=self
        )
        temp_task.completed = False
        temp_task.display_task.value = False
        self.tasks.controls.append(temp_task)

        self.new_task.value = ""  # czyścimy pole
        self.new_task.focus()    # ustawiamy fokus
        self.update()

        # równolegle wysyłamy dodanie do backendu, jak się wszystko powiedzie to
        # przypisujemy id zwrócone przez backend, a jak fail to usuwamy zadanie
        def add_async():
            data, error = ApiClient.make_request(
                "POST", f"{BACKEND_URL}/todos",
                {"title": new_title}
            )
            if not error:
                temp_task.id = data["id"]
                temp_task.completed = data.get("completed", False)
                temp_task.display_task.value = temp_task.completed
                self.update()
            else:
                if temp_task in self.tasks.controls:
                    self.tasks.controls.remove(temp_task)
                self.update()

        threading.Thread(target=add_async, daemon=True).start()

    def task_status_change(self, task):
        # callback gdy zmieniamy checkbox zrobione/nie
        self.update()

    def task_delete(self, task):
        # usuwanie zadania z UI i aktualizacja widoku
        if task in self.tasks.controls:
            self.tasks.controls.remove(task)
        self.update()

    def tabs_changed(self, e):
        # zmiana zakładek (filtr widoku) - odświeżamy widok
        self.update()

    def clear_clicked(self, e):
        # usuwanie wszystkich zadań wykonanych

        completed_tasks = [task for task in self.tasks.controls if task.completed]
        for task in completed_tasks:
            self.task_delete(task)

        def clear_async():
            # równolegle usuwamy z backendu zadania wykonane
            for task in completed_tasks:
                if task.id is not None:
                    ApiClient.make_request("DELETE", f"{BACKEND_URL}/todos/{task.id}")

        threading.Thread(target=clear_async, daemon=True).start()

    def before_update(self):
        # przed każdą aktualizacją UI ukrywamy lub pokazujemy zadania wg filtra
        # również liczmy ile jest aktywnych zadań i pokazujemy na dole

        status = self.filter.tabs[self.filter.selected_index].text.lower()
        count = 0
        for task in self.tasks.controls:
            if status == "active to-dos":
                task.visible = not task.completed
            elif status == "all to-dos":
                task.visible = True
            elif status == "completed to-dos":
                task.visible = task.completed
            if not task.completed:
                count += 1
        self.items_left.value = f"{count} active item(s) left"


def main(page: ft.Page):
    # ustawienia okna i motywu
    page.title = "ToDo!"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.theme_mode = ft.ThemeMode.DARK

    # dodajemy naszą aplikację TodoApp na stronę/okno
    page.add(TodoApp(page))


if __name__ == "__main__":
    # uruchamianie aplikacji w trybie webowym na porcie 10000
    # jeśli chcesz desktop, wywołaj ft.app(target=main) bez argumentów
    ft.app(target=main, view=ft.WEB_BROWSER, port=10000, assets_dir="assets")