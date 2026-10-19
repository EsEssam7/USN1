"""Generator screen: controls, result cards and the detail panel."""
from __future__ import annotations

import queue
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core import export
from app.core.export import matrix_to_markdown
from app.core.filters import FilterOptions, parse_char_set
from app.core.generator import MODE_BRANDABLE, MODE_PATTERN, GenerationRequest, generate
from app.core.patterns import PRESETS, PatternError, estimate_space, format_count, parse_pattern
from app.core.phonetics import arabic_reading
from app.core.platform_rules import get_rule, load_rules
from app.core.scoring import score_name
from app.core.similarity import find_similar
from app.i18n.i18n import is_rtl, t
from app.services.availability import Status
from app.ui import theme
from app.ui.widgets import STATUS_LABELS, UsernameCard, anchor

if TYPE_CHECKING:
    from app.ui.app import USNApp

BATCH = 50
MAX_CARDS = 300
POLL_MS = 120
CHECK_CONFIRM_THRESHOLD = 80  # name x platform requests before we ask first


class GeneratorView(theme.Frame):
    """Left: controls. Centre: results. Right: details for the selected username."""

    def __init__(self, master, app: "USNApp"):
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.cards: dict[str, UsernameCard] = {}
        self.seen: set[str] = set()
        self.selected: str | None = None
        self.checks: dict[str, list] = {}
        self.scores: dict[str, object] = {}
        self._queue: queue.Queue = queue.Queue()
        self._checking = False
        self._cancel = threading.Event()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_controls()
        self._build_results()
        self._build_detail()
        self.load_settings_defaults()

    # ------------------------------------------------------------------ layout
    def _build_controls(self) -> None:
        panel = ctk.CTkScrollableFrame(self, width=300, fg_color=theme.SURFACE, corner_radius=theme.RADIUS)
        panel.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        self.controls = panel

        self.mode_seg = ctk.CTkSegmentedButton(panel, values=[t("gen.mode.pattern"), t("gen.mode.brandable")],
                                               command=lambda _v: self._on_mode())
        self.mode_seg.set(t("gen.mode.pattern"))
        self.mode_seg.pack(fill="x", padx=12, pady=(12, 8))

        self._section_label(panel, t("gen.pattern"))
        self.pattern_entry = ctk.CTkEntry(panel, placeholder_text="CVCV")
        self.pattern_entry.pack(fill="x", padx=12)
        self.preset_menu = ctk.CTkOptionMenu(panel, values=list(PRESETS), command=self._on_preset)
        self.preset_menu.set(t("gen.presets"))
        self.preset_menu.pack(fill="x", padx=12, pady=(6, 4))
        trending = self.app.trending_names()
        self.trend_menu = ctk.CTkOptionMenu(panel, values=trending or ["-"], command=self._on_trend)
        self.trend_menu.set(t("gen.trending"))
        self.trend_menu.pack(fill="x", padx=12, pady=(0, 4))

        lengths = theme.Frame(panel, fg_color="transparent")
        lengths.pack(fill="x", padx=12, pady=4)
        self.min_entry = ctk.CTkEntry(lengths, width=120, placeholder_text=t("gen.min"))
        self.max_entry = ctk.CTkEntry(lengths, width=120, placeholder_text=t("gen.max"))
        self.min_entry.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.max_entry.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self._section_label(panel, t("gen.platforms"))
        self.platform_vars: dict[str, ctk.BooleanVar] = {}
        grid = theme.Frame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=12)
        for i, key in enumerate(load_rules()):
            var = ctk.BooleanVar(value=False)
            self.platform_vars[key] = var
            ctk.CTkCheckBox(grid, text=get_rule(key).name, variable=var, font=ctk.CTkFont(size=12),
                            checkbox_width=16, checkbox_height=16,
                            command=self._on_platforms_changed).grid(row=i // 2, column=i % 2, sticky="w", pady=3, padx=2)

        self.filters_frame = theme.Frame(panel, fg_color="transparent")
        self.filters_open = False
        self.filter_btn = ctk.CTkButton(panel, text=t("gen.filters"), fg_color="transparent",
                                        text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                                        hover_color=theme.SURFACE_HOVER, command=self._toggle_filters)
        self.filter_btn.pack(fill="x", padx=12, pady=(12, 4))
        self._build_filters(self.filters_frame)

        self.words_var = ctk.BooleanVar(value=False)
        self.words_check = ctk.CTkCheckBox(panel, text=t("gen.words_only"), variable=self.words_var,
                                           font=ctk.CTkFont(size=12))
        self.arabic_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(panel, text=t("gen.show_arabic"), variable=self.arabic_var,
                        font=ctk.CTkFont(size=12)).pack(anchor="w", padx=12, pady=6)

        self.generate_btn = ctk.CTkButton(panel, text=t("gen.generate"), fg_color=theme.BUTTON,
                                          text_color=theme.BUTTON_TEXT, hover_color=theme.BUTTON_HOVER,
                                          command=self.generate_new)
        self.generate_btn.pack(fill="x", padx=12, pady=(8, 4))
        self.check_btn = ctk.CTkButton(panel, text=t("gen.check_all"), fg_color="transparent",
                                       text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                                       hover_color=theme.SURFACE_HOVER, command=self.check_visible)
        self.check_btn.pack(fill="x", padx=12, pady=4)

        self.space_label = ctk.CTkLabel(panel, text="", wraplength=260, justify="left",
                                        font=ctk.CTkFont(size=12), text_color=theme.MUTED, anchor=anchor())
        self.space_label.pack(fill="x", padx=12, pady=(8, 12))

    def _build_filters(self, parent) -> None:
        self.f_start = self._entry(parent, t("filter.starts_with"))
        self.f_end = self._entry(parent, t("filter.ends_with"))
        self.f_contains = self._entry(parent, t("filter.contains"))
        self.f_exclude = self._entry(parent, t("filter.exclude_chars"))
        self.f_no_repeat = ctk.BooleanVar(value=False)
        self.f_no_digits = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(parent, text=t("filter.no_repeats"), variable=self.f_no_repeat,
                        font=ctk.CTkFont(size=12), command=self._update_filter_count).pack(anchor="w", padx=12, pady=3)
        ctk.CTkCheckBox(parent, text=t("filter.no_digits"), variable=self.f_no_digits,
                        font=ctk.CTkFont(size=12), command=self._update_filter_count).pack(anchor="w", padx=12, pady=3)
        ctk.CTkButton(parent, text=t("gen.reset_filters"), height=28, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                      hover_color=theme.SURFACE_HOVER, font=ctk.CTkFont(size=11),
                      command=self.reset_filters).pack(fill="x", padx=12, pady=(8, 6))
        for entry in (self.f_start, self.f_end, self.f_contains, self.f_exclude):
            entry.bind("<KeyRelease>", lambda _e: self._update_filter_count())

    def _active_filter_count(self) -> int:
        texts = [self.f_start, self.f_end, self.f_contains, self.f_exclude]
        count = sum(1 for e in texts if e.get().strip())
        count += int(bool(self.f_no_repeat.get())) + int(bool(self.f_no_digits.get()))
        return count

    def _update_filter_count(self) -> None:
        n = self._active_filter_count()
        self.filter_btn.configure(text=t("gen.filters_active", count=n) if n else t("gen.filters"))

    def reset_filters(self) -> None:
        for entry in (self.f_start, self.f_end, self.f_contains, self.f_exclude):
            entry.delete(0, "end")
        self.f_no_repeat.set(False)
        self.f_no_digits.set(False)
        self._update_filter_count()

    def _build_results(self) -> None:
        wrap = theme.Frame(self, fg_color="transparent")
        wrap.grid(row=0, column=1, sticky="nsew", padx=6, pady=12)
        wrap.grid_rowconfigure(2, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        head = theme.Frame(wrap, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(head, text=t("nav.generator"), font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=theme.TEXT).pack(side="left" if not is_rtl() else "right")
        # Messages (problems, warnings, empty results) appear here, above the results.
        self.status_label = ctk.CTkLabel(wrap, text="", wraplength=760, justify="left", anchor=anchor(),
                                         font=ctk.CTkFont(size=12), text_color=theme.TEXT,
                                         fg_color=theme.SURFACE, corner_radius=10)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.more_btn = ctk.CTkButton(head, text=t("gen.load_more"), width=120, fg_color="transparent",
                                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                                      hover_color=theme.SURFACE_HOVER, command=self.load_more)
        self.more_btn.pack(side="right" if not is_rtl() else "left")
        self.sort_seg = ctk.CTkSegmentedButton(head, values=[t("gen.sort_generated"), t("gen.sort_score")],
                                               width=230, command=lambda _v: self.apply_sort())
        self.sort_seg.set(t("gen.sort_generated"))
        self.sort_seg.pack(side="right" if not is_rtl() else "left", padx=6)
        _copy_btn = ctk.CTkButton(head, text=t("gen.copy_visible"), width=120, fg_color="transparent",
                                  text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                                  hover_color=theme.SURFACE_HOVER, command=self.copy_visible)
        _copy_btn.pack(side="right" if not is_rtl() else "left", padx=6)
        self.results = ctk.CTkScrollableFrame(wrap, fg_color=theme.BG)
        self.results.grid(row=2, column=0, sticky="nsew")

    def _build_detail(self) -> None:
        self.detail = ctk.CTkScrollableFrame(self, width=300, fg_color=theme.SURFACE, corner_radius=theme.RADIUS)
        self.detail.grid(row=0, column=2, sticky="ns", padx=(6, 12), pady=12)
        self.show_detail(None)

    # ----------------------------------------------------------------- helpers
    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=theme.MUTED, anchor=anchor()).pack(fill="x", padx=12, pady=(10, 2))

    def _entry(self, parent, placeholder: str) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder)
        entry.pack(fill="x", padx=12, pady=3)
        return entry

    def load_settings_defaults(self) -> None:
        s = self.app.repo.settings
        self.pattern_entry.delete(0, "end")
        self.pattern_entry.insert(0, s.get("default_pattern", "CVCV"))
        self.min_entry.insert(0, "4")
        self.max_entry.insert(0, "8")
        for key in s.get("default_platforms", []):
            if key in self.platform_vars:
                self.platform_vars[key].set(True)

    def _toggle_filters(self) -> None:
        self.filters_open = not self.filters_open
        if self.filters_open:
            self.filters_frame.pack(fill="x", after=self.filter_btn)
        else:
            self.filters_frame.pack_forget()

    def _on_mode(self) -> None:
        """Show brandable-only options only when Brandable mode is selected."""
        if self.mode_seg.get() == t("gen.mode.brandable"):
            self.words_check.pack(anchor="w", padx=12, pady=(6, 0), after=self.trend_menu)
        else:
            self.words_check.pack_forget()
        self._update_space()

    def _on_preset(self, choice: str) -> None:
        self.pattern_entry.delete(0, "end")
        self.pattern_entry.insert(0, PRESETS.get(choice, choice))
        self._update_space()

    def _on_trend(self, choice: str) -> None:
        pattern = self.app.trending_pattern(choice)
        if pattern:
            self.pattern_entry.delete(0, "end")
            self.pattern_entry.insert(0, pattern["pattern"])
            self.status_label.configure(text=pattern["text"])
            self._update_space()

    def _on_platforms_changed(self) -> None:
        self._update_space()

    def selected_platforms(self) -> list[str]:
        return [k for k, v in self.platform_vars.items() if v.get()]

    def _update_space(self) -> None:
        if self.mode_seg.get() != t("gen.mode.pattern"):
            return
        try:
            space = estimate_space(parse_pattern(self.pattern_entry.get()))
            self.space_label.configure(text=t("gen.space", count=format_count(space)))
        except PatternError:
            self.space_label.configure(text="")

    def _build_request(self) -> GenerationRequest:
        def ints(entry, default: int) -> int:
            try:
                return int(entry.get())
            except ValueError:
                return default

        min_len, max_len = ints(self.min_entry, 4), ints(self.max_entry, 8)
        if min_len > max_len:
            raise ValueError("min > max")
        exclude = parse_char_set(self.f_exclude.get())
        filters = FilterOptions(
            starts_with=self.f_start.get().strip(), ends_with=self.f_end.get().strip(),
            contains=self.f_contains.get().strip(), exclude_chars=exclude,
            no_repeated_chars=bool(self.f_no_repeat.get()), no_consecutive_digits=bool(self.f_no_digits.get()),
            blocklist=self.app.blocklist,
        )
        mode = MODE_BRANDABLE if self.mode_seg.get() == t("gen.mode.brandable") else MODE_PATTERN
        return GenerationRequest(
            mode=mode, words_only=bool(self.words_var.get()) and mode == MODE_BRANDABLE,
            pattern=self.pattern_entry.get().strip() or "CVCV",
            min_length=min_len, max_length=max_len, platforms=self.selected_platforms(),
            filters=filters, count=BATCH, syllables=self.app.syllables, exclude=set(self.seen),
        )

    # ------------------------------------------------------------ generation
    def generate_new(self) -> None:
        self.clear_results()
        self._run_generation()

    def load_more(self) -> None:
        if len(self.cards) >= MAX_CARDS:
            self.status_label.configure(text=t("gen.limit", max=MAX_CARDS))
            return
        self._run_generation()

    def ordered_names(self) -> list[str]:
        """Visible usernames in the order chosen with the sort control."""
        names = list(self.cards)
        if self.sort_seg.get() == t("gen.sort_score"):
            names.sort(key=lambda n: self.scores[n].total, reverse=True)
        return names

    def apply_sort(self) -> None:
        """Re-pack the cards in the chosen order."""
        for name in self.ordered_names():
            card = self.cards[name]
            card.pack_forget()
            card.pack(fill="x", padx=6, pady=5)

    def _run_generation(self) -> None:
        try:
            request = self._build_request()
            result = generate(request, rng=self.app.rng, dictionary=self.app.dictionary)
        except (PatternError, ValueError) as exc:
            self.status_label.configure(text=str(exc))
            return
        for name in result.usernames:
            self.seen.add(name)
            self._add_card(name, use_arabic=bool(self.arabic_var.get()))
        self._show_status(result, request)
        if result.usernames:
            self.app.repo.add_history({
                "mode": request.mode, "pattern": request.pattern,
                "platforms": request.platforms, "count": len(result.usernames),
                "min_length": request.min_length, "max_length": request.max_length,
                "filters": {"starts_with": request.filters.starts_with,
                            "ends_with": request.filters.ends_with,
                            "contains": request.filters.contains},
                "usernames": result.usernames[:BATCH],
            })

    def _show_status(self, result, request) -> None:
        lines = []
        if result.space_estimate:
            lines.append(t("gen.space", count=format_count(result.space_estimate)))
        for key, kwargs in result.warnings:
            lines.append(t(key, **kwargs))
        has_reason = any(key.startswith("gen.problem") or key == "gen.warn.no_words" for key, _ in result.warnings)
        if not result.usernames and not has_reason:
            lines.append(t("gen.none"))
            if result.rejected:
                top = result.rejected.most_common(1)[0][0]
                lines.append(t("gen.top_rejection", reason=t(f"reason.{top}")))
        self.status_label.configure(text="\n".join(lines))

    def _add_card(self, name: str, use_arabic: bool) -> None:
        score = score_name(name, self.app.dictionary)
        self.scores[name] = score
        arabic = arabic_reading(name) if use_arabic else None
        card = UsernameCard(self.results, self.app, name, score.total, arabic,
                            reasons=score.top_reasons(2))
        card.pack(fill="x", padx=6, pady=5)
        card.set_badges(self.selected_platforms(), self.app.repo.used_platforms(name),
                        self._taken_keys(name))
        self.cards[name] = card

    def clear_results(self) -> None:
        for card in self.cards.values():
            card.destroy()
        self.cards.clear()
        self.seen.clear()
        self.checks.clear()
        self.select_username(None)

    def refresh_cards(self) -> None:
        for name, card in self.cards.items():
            card.refresh_star()
            card.set_badges(self.selected_platforms(), self.app.repo.used_platforms(name),
                            self._taken_keys(name))

    def _taken_keys(self, name: str) -> list[str]:
        return [c.platform for c in self.checks.get(name, []) if c.status is Status.TAKEN]

    # ----------------------------------------------------------- selection
    def select_username(self, name: str | None) -> None:
        self.selected = name
        for n, card in self.cards.items():
            card.set_selected(n == name)
        self.show_detail(name)

    def show_detail(self, name: str | None) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        if not name:
            ctk.CTkLabel(self.detail, text=t("detail.no_selection"), text_color=theme.MUTED,
                         wraplength=250, justify="left").pack(padx=14, pady=20)
            return
        ctk.CTkLabel(self.detail, text=name, font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=theme.TEXT).pack(anchor="w", padx=14, pady=(14, 2))
        ctk.CTkLabel(self.detail, text=t("detail.title"), text_color=theme.MUTED,
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=14)

        score = self.scores.get(name)
        if score:
            for factor, value in score.factors.items():
                row = theme.Frame(self.detail, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=1)
                ctk.CTkLabel(row, text=factor.replace("_", " "), font=ctk.CTkFont(size=11),
                             text_color=theme.MUTED).pack(side="left")
                ctk.CTkLabel(row, text=str(value), font=ctk.CTkFont(size=11),
                             text_color=theme.TEXT).pack(side="right")

        sim = find_similar(name, self.app.saved_names())
        for match in sim[:2]:
            text = t("detail.anagram", name=match.other) if match.anagram else \
                t("detail.similar", name=match.other, ratio=match.ratio)
            ctk.CTkLabel(self.detail, text=text, wraplength=260, text_color=theme.MUTED,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=14, pady=2)

        used = self.app.repo.used_platforms(name)
        if used:
            ctk.CTkLabel(self.detail, text=t("detail.used_on", platforms=", ".join(used)),
                         font=ctk.CTkFont(size=11), text_color=theme.MUTED).pack(anchor="w", padx=14, pady=2)

        ctk.CTkLabel(self.detail, text=t("detail.matrix"), font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=theme.TEXT).pack(anchor="w", padx=14, pady=(12, 4))
        rows = []
        results_by_platform = {c.platform: c for c in self.checks.get(name, [])}
        platform_keys = list(self.selected_platforms()) or list(results_by_platform)
        for key in platform_keys:
            rule = get_rule(key)
            res = results_by_platform.get(key)
            rule_ok = rule.is_valid(name)
            if res:
                status_text = t(STATUS_LABELS[res.status])
            elif not rule_ok:
                status_text = t("status.invalid")
            else:
                status_text = t("status.not_checked")
            row = theme.Frame(self.detail, height=0, fg_color=theme.BG, corner_radius=8, border_width=1,
                               border_color=theme.BORDER)
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row, text=rule.name, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=theme.TEXT).pack(anchor="w", padx=10, pady=(6, 0))
            if res and res.status is Status.NOT_CHECKABLE:
                detail_text = t("detail.no_public_page")
            else:
                detail_text = status_text + (f" · {res.detail}" if res and res.detail else "")
            ctk.CTkLabel(row, text=detail_text, font=ctk.CTkFont(size=11), text_color=theme.MUTED,
                         wraplength=230, justify="left").pack(anchor="w", padx=10)
            url = rule.profile_link(name)
            if url:
                ctk.CTkButton(row, text=t("detail.verify"), height=26, fg_color="transparent",
                              text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                              hover_color=theme.SURFACE_HOVER, font=ctk.CTkFont(size=11),
                              image=theme.ui_icon("external-link", 14),
                              command=lambda u=url: webbrowser.open(u)).pack(anchor="w", padx=10, pady=(4, 6))
            rows.append((rule.name, status_text, url or ""))

        actions = theme.Frame(self.detail, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkButton(actions, text=t("detail.export_md"), height=30, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                      hover_color=theme.SURFACE_HOVER, font=ctk.CTkFont(size=11),
                      command=lambda: self._copy_matrix(name, rows)).pack(fill="x", pady=2)
        ctk.CTkButton(actions, text=t("detail.save_csv"), height=30, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                      hover_color=theme.SURFACE_HOVER, font=ctk.CTkFont(size=11),
                      command=lambda: self._save_csv(name, rows)).pack(fill="x", pady=2)
        ctk.CTkButton(actions, text=t("detail.reserve"), height=30, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
                      hover_color=theme.SURFACE_HOVER, font=ctk.CTkFont(size=11),
                      command=lambda: self.app.reserve_dialog(name)).pack(fill="x", pady=2)
        ctk.CTkLabel(self.detail, text=t("detail.disclaimer"), wraplength=260, justify="left",
                     font=ctk.CTkFont(size=11), text_color=theme.MUTED).pack(anchor="w", padx=14, pady=(8, 14))

    def _save_csv(self, name: str, rows) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{name}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(export.matrix_to_csv(rows))

    def copy_visible(self) -> None:
        """Copy every username currently shown, one per line."""
        self.app.copy_text(export.as_plain_list(list(self.cards)))

    def _copy_matrix(self, name: str, rows) -> None:
        text = matrix_to_markdown(name, rows)
        self.clipboard_clear()
        self.clipboard_append(text)

    # ------------------------------------------------------- availability
    def check_visible(self) -> None:
        names = list(self.cards)
        platforms = self.selected_platforms()
        if not platforms or not names:
            self.status_label.configure(text=t("detail.no_selection"))
            return
        total = len(names) * len(platforms)
        if total > CHECK_CONFIRM_THRESHOLD and not messagebox.askyesno(
                "USN", t("check.confirm_many", names=len(names), platforms=len(platforms), total=total)):
            return
        self._start_checks(names, platforms)

    def check_username(self, name: str) -> None:
        platforms = self.selected_platforms() or list(load_rules())
        self._start_checks([name], platforms)

    def _start_checks(self, names: list[str], platforms: list[str]) -> None:
        if self._checking:
            return
        self._checking = True
        self._cancel.clear()
        self.status_label.configure(text=t("gen.checking"))
        self.check_btn.configure(state="disabled")

        def worker() -> None:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(self.app.checker.check_many, n, platforms): n for n in names}
                for fut, name in futures.items():
                    if self._cancel.is_set():
                        break
                    self._queue.put((name, fut.result()))
            self._queue.put(None)

        threading.Thread(target=worker, daemon=True).start()
        self.after(POLL_MS, self._poll_checks)

    def _poll_checks(self) -> None:
        done = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                done = True
                break
            name, results = item
            self.checks[name] = results
            if name in self.cards:
                self.cards[name].set_badges(self.selected_platforms(), self.app.repo.used_platforms(name),
                                            self._taken_keys(name))
            if name == self.selected:
                self.show_detail(name)
        if done:
            self._checking = False
            self.check_btn.configure(state="normal")
            self.status_label.configure(text=t("detail.disclaimer"))
        else:
            self.after(POLL_MS, self._poll_checks)

