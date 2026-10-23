# Настройки zsh в песочнице тренажёра. Сначала подключаем обычный ~/.zshrc
# владельца (alias, тема, Oh My Zsh), потом — свои команды и хуки.

zstyle ':omz:update' mode disabled      # не спрашивать про обновление посреди задачи
# Корень игры — от пути этого файла (termit_app/shell/.zshrc), не из окружения: хук зовётся
# через python -I с корнем аргументом (termit_app/paths.py, BOOT — та же строка).
typeset -g _tr_root=${${(%):-%x}:A:h:h:h}
typeset -g _tr_boot='import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module(sys.argv.pop(1), run_name="__main__", alter_sys=True)'
DISABLE_AUTO_UPDATE=true

# Кэш Oh My Zsh и compdump — только в песочнице: файлы в настоящем доме потом читает обычный
# zsh владельца без всякой защиты, дописанная туда строка была бы побегом (ревью безопасности).
# Готовый compdump владельца копируем (только чтение), чтобы не строить его заново.
# Параметры, что есть ДО ~/.zshrc владельца: собственные zsh (KEYTIMEOUT и т.п.) и уже
# отфильтрованное окружение. Чистка секретов ниже их не трогает.
typeset -gA _tr_before
for _tr_v in ${(k)parameters}; do _tr_before[$_tr_v]=1; done
_tr_zd=$ZDOTDIR
ZDOTDIR=$TERMIT_BOX/.termit/zdot
ZSH_CACHE_DIR=$TERMIT_BOX/.termit/omz-cache
ZSH_COMPDUMP=$TERMIT_BOX/.termit/zcompdump
mkdir -p $ZDOTDIR $ZSH_CACHE_DIR/completions 2>/dev/null
() {
  local dumps=($HOME/.zcompdump-*~*.zwc(N.om))
  [[ -n $dumps[1] && ! -e $ZSH_COMPDUMP ]] && cp $dumps[1] $ZSH_COMPDUMP 2>/dev/null
}
if [[ -z $TERMIT_BARE && -r $HOME/.zshrc ]]; then
  source $HOME/.zshrc
fi
# Владелец 23.10: «зашёл в man — как выйти, не сказано». Внизу less (в нём man) вместо голого «:»
# — подсказка; -P после чужих опций LESS, поэтому побеждает наша.
export LESS="${LESS:+$LESS }-Psq — выйти · /слово — поиск · пробел — дальше\$"
# zsh-autosuggestions оборачивает Ctrl+W и Ctrl+Y — и стёртое подряд перестаёт склеиваться в
# кармане: Ctrl+Y возвращает лишь последний кусок (владелец 23.10, урок cut_paste). Плагину —
# не трогать стирание и вставку; свои обёртки гасят серую подсказку (иначе она съезжает) и
# помечают себя как kill/yank (zle -f) — так склейка и Ctrl+Y дважды работают.
# Уже починено в ~/.zshrc игрока (backward-kill-word в списке) — не трогаем: его обёртки главнее.
if (( ${+ZSH_AUTOSUGGEST_IGNORE_WIDGETS} && ! ${ZSH_AUTOSUGGEST_IGNORE_WIDGETS[(Ie)backward-kill-word]} )); then
  ZSH_AUTOSUGGEST_IGNORE_WIDGETS+=(backward-kill-word kill-word kill-line backward-kill-line
    kill-whole-line yank)
  for _tr_kw in backward-kill-word kill-word kill-line backward-kill-line kill-whole-line; do
    eval "_tr_clear_$_tr_kw() { POSTDISPLAY=; zle .$_tr_kw; zle -f kill }"
    zle -N $_tr_kw _tr_clear_$_tr_kw
  done
  _tr_clear_yank() { POSTDISPLAY=; zle .yank; zle -f yank }
  zle -N yank _tr_clear_yank
  unset _tr_kw
fi
# Ctrl+R, Ctrl+T и Alt+C в игре — штатные, даже если ~/.zshrc владельца подключил fzf напрямую
# (наш ~/.config/termit/shell.zsh внутри игры выходит сам). Виджеты fzf-* снимаем и возвращаем
# штатные: Ctrl+R — поиск по истории (в vicmd — redo), Ctrl+T и Alt+C в emacs — transpose-chars
# и capitalize-word, в vi-раскладках просто убираем. Чужие привязки (не fzf-*) не трогаем.
# zoxide владельца тут тоже выключен: его хук писал бы базу в настоящий дом (запись туда
# запрещена), а «прыжки назад» в игре — встроенные: auto_pushd, cd -, dirs -v.
# Зовём сейчас и ещё раз на первом приглашении: zsh-vi-mode, zinit turbo, zsh-defer
# привязывают клавиши позже, уже из precmd.
_tr_unfzf() {
  local km key w f
  for km in emacs viins vicmd; do
    w=${${(z)"$(bindkey -M $km '^R' 2>/dev/null)"}[2]}
    if [[ $w == fzf-* && $km == vicmd ]]; then
      bindkey -M vicmd '^R' redo
    elif [[ $w == fzf-* ]]; then
      bindkey -M $km '^R' history-incremental-search-backward
    fi
    for key in '^T' '\ec'; do
      w=${${(z)"$(bindkey -M $km $key 2>/dev/null)"}[2]}
      [[ $w == fzf-* ]] || continue
      if [[ $km == emacs && $key == '^T' ]]; then
        bindkey -M emacs '^T' transpose-chars
      elif [[ $km == emacs ]]; then
        bindkey -M emacs '\ec' capitalize-word
      else
        bindkey -M $km -r $key
      fi
    done
  done
  [[ -n $_tr_zo_on ]] && return     # свой zoxide песочницы (z_jump) уже включён — не трогаем
  for f in z zi cd cdi; do
    [[ ${functions[$f]} == *__zoxide_* ]] && unfunction $f
  done
  for f in z zi; do
    [[ ${aliases[$f]} == *__zoxide_* ]] && unalias $f
  done
  chpwd_functions=(${chpwd_functions:#__zoxide_hook})
  precmd_functions=(${precmd_functions:#__zoxide_hook})
} 2>/dev/null
_tr_unfzf_once() {
  _tr_unfzf
  precmd_functions=(${precmd_functions:#_tr_unfzf_once})
  unfunction _tr_unfzf_once
}
_tr_unfzf
setopt auto_pushd pushd_ignore_dups
# FB2: клавиши строки, которым учит игра (keys). Option+← → в iTerm2 шлёт ^[[1;3D/C, с «Option
# как Meta» — ^[^[[D/C, fn+← → (Home/End) — ^[[H/^[[F и ^[OH/^[OF; без привязки zsh печатает
# мусор. Привязываем только то, что не занято ~/.zshrc владельца (чужое не трогаем).
_tr_keys() {
  local km key w
  local -A want=('^[[1;3D' backward-word '^[[1;3C' forward-word
                 '^[^[[D' backward-word '^[^[[C' forward-word
                 '^[[H' beginning-of-line '^[[F' end-of-line
                 '^[OH' beginning-of-line '^[OF' end-of-line)
  for km in emacs viins; do
    for key in ${(k)want}; do
      w=${${(z)"$(bindkey -M $km $key 2>/dev/null)"}[2]}
      [[ -z $w || $w == undefined-key ]] && bindkey -M $km $key $want[$key]
    done
  done
} 2>/dev/null
_tr_keys
ZDOTDIR=$_tr_zd
unset _tr_zd

# Дом — внутри песочницы: cd ~ и ~/… не уходят к настоящим файлам.
export HOME=$TERMIT_BOX/.termit/home
# FB2 (2): «набрал cd без пути — перекинуло в дом песочницы, а там не работает ls». ls там
# работает, но дом у большинства задач пуст — и молчит. Пустой дом (без единого файла, даже
# скрытого — иначе это подсказка к задаче) объясняем: где ты и как вернуться.
_tr_home_empty() {
  [[ $PWD == $HOME ]] || return 1
  local -a f=($HOME/*(DN[1]))
  (( ! $#f ))
}
_tr_home_note() {
  _tr_home_empty || return 0
  print -r -- "(Ты в доме песочницы — сюда ведут cd без пути и cd ~. Дом пока пуст, поэтому ls молчит — это не поломка. Назад, где был: cd -)"
}
chpwd_functions+=(_tr_home_note)

# PostgreSQL (часть 9б): ~/.zshrc владельца мог выставить PGHOST, PGPASSWORD, PGSERVICE и т.п.
# (облачная база) — всё PG* и PSQL* снимаем; учебный сервер задачи (если он есть) — только
# из TERMIT_PG*, их задаёт родитель. Пейджер psql: длинные строки не переносить, короткий
# вывод — без пейджера, выход — q.
unset -m 'PG*' 'PSQL*' 2>/dev/null
if [[ -n $TERMIT_PGHOST ]]; then
  export PGHOST=$TERMIT_PGHOST PGPORT=$TERMIT_PGPORT PGUSER=$TERMIT_PGUSER
  export PGDATABASE=$TERMIT_PGDATABASE PSQL_PAGER='less -SFX'
fi

# ~/.zshrc владельца мог выставить секреты (экспортом или просто переменной) — чистим.
# Имена, не значения. Не трогаем только параметры самого zsh (special/readonly и всё, что было
# до ~/.zshrc) и переменные терминала — а ZSH_*_API_KEY, _*_TOKEN и т.п. удаляются.
_tr_scrub() {
  local v t
  for v in ${(k)parameters}; do
    t=${parameters[$v]}
    [[ $t == *special* || $t == *readonly* || -n ${_tr_before[$v]} ]] && continue
    case $v in
      (v|t|TERMIT_*|ITERM_*|TERM_*|LC_*) continue ;;
    esac
    if [[ ${(U)v} == *(TOKEN|KEY|SECRET|PASS|AUTH|CRED|DSN|_URL|COOKIE|SESSION|PRIVATE|WEBHOOK)* ||
          ${(U)v} == (*_|)PAT(_*|) ]]; then
      unset $v 2>/dev/null
    fi
  done
}
_tr_scrub
unfunction _tr_scrub
unset _tr_before _tr_v
unset SSH_AUTH_SOCK SSH_AGENT_PID GIT_ASKPASS SSH_ASKPASS SUDO_ASKPASS 2>/dev/null
# Временные файлы (и here-doc zsh) — только в песочнице: вне её запись запрещена.
export TMPDIR=$TERMIT_BOX/.termit/tmp/
TMPPREFIX=$TERMIT_BOX/.termit/tmp/zsh
export GIT_CONFIG_NOSYSTEM=1
# Python и pip в песочнице (часть 7, A1): pip не ищет сеть дольше секунд (её нет — профиль) и не
# читает конфиги владельца; флаги --no-index --find-links учим явно, глобально их не ставим.
# Окружение Python владельца (OMZ-плагины python/pip, ~/.zshrc) в игру не попадает: все PIP_* и
# PYTHON* снимаем (PIP_REQUIRE_VIRTUALENV, PIP_NO_INDEX, PYTHONUSERBASE и т.п. делали бы уроки
# разными на разных машинах), из PYTHON* родитель задаёт только PYTHONDONTWRITEBYTECODE.
# alias и функции python/pip владельца сильнее PATH — их тоже снимаем: python3, pip и pip3 вне
# venv — закреплённые обёртки .termit/bin (часть 7, I1 ревью P1).
unset -m 'PIP_*' 'PYTHON*' 2>/dev/null
unset VIRTUAL_ENV 2>/dev/null
export PYTHONDONTWRITEBYTECODE=1
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_RETRIES=0 PIP_TIMEOUT=3 PIP_CONFIG_FILE=/dev/null
unalias python python3 pip pip3 2>/dev/null
unfunction python python3 pip pip3 2>/dev/null

HISTFILE=$TERMIT_BOX/.termit/history
HISTSIZE=1000
SAVEHIST=1000
[[ -r $HISTFILE ]] && fc -R $HISTFILE

path=($TERMIT_BOX/.termit/bin $path)

# Окружение задачи (часть 7): переменные урока пишет родитель в .termit/env.zsh (export
# ИМЯ=значение). Подключается после чистки секретов и своих настроек — учебные demo-ключи
# остаются, а ~/.zshrc владельца их не перебивает. reset переписывает файл.
[[ -r $TERMIT_BOX/.termit/env.zsh ]] && source $TERMIT_BOX/.termit/env.zsh

# z_jump: zoxide — только по флагу родителя (задача с утилитой zoxide и zoxide найден), только
# здесь и со своей базой внутри песочницы: в настоящий дом он не пишет. zoxide владельца снят
# выше (_tr_unfzf); одноразовый хук первого приглашения наш уже не тронет (_tr_zo_on).
if [[ -n $TERMIT_ZOXIDE ]] && (( $+commands[zoxide] )); then
  export _ZO_DATA_DIR=$TERMIT_BOX/.termit/zoxide
  mkdir -p $_ZO_DATA_DIR 2>/dev/null
  eval "$(zoxide init zsh)"
  _tr_zo_on=1
fi

unalias task hint ans reset giveup skip quit bug loot memory ask keys ext book lesson 2>/dev/null
_tr() { "$TERMIT_PY" -I -B -c "$_tr_boot" "$_tr_root" termit_app.hook "$@" }
task()   { _tr task }
hint()   { _tr hint }
ans()    { _tr ans "$*" }
reset()  { _tr reset && { cd "$(<$TERMIT_BOX/.termit/start_dir)" 2>/dev/null || cd "$TERMIT_BOX" } }
giveup() { _tr giveup }
skip()   { _tr skip }
quit()   { _tr quit }
# FB3 (1): bug без текста — вопрос и одна строка через read -r: оболочка её не разбирает
# (| && $() кавычки * — дословно), в историю она не попадает. Пустой Enter и Ctrl+C — отмена.
bug() {
  if (( $# )); then
    _tr bug "$*"
    return
  fi
  _tr bug_ask
  setopt localoptions localtraps
  trap 'print -r -- "(отменено — замечание не отправлено)"; return 130' INT
  local _tr_note=
  read -r "_tr_note?> " || { print -r -- "(отменено — замечание не отправлено)"; return 1 }
  if [[ -z ${_tr_note//[[:space:]]/} ]]; then
    print -r -- "(пусто — отменено, замечание не отправлено)"
    return 0
  fi
  _tr bug "$_tr_note"
}
loot()   { _tr loot "$*" }
memory() { _tr memory "$*" }
ask()    { _tr ask "$*" }
keys()   { _tr keys "$*" }
ext()    { _tr ext }
book()   { _tr book "$*" }
lesson() { _tr lesson }
# Без noglob «bug почему не работает?» падает с «no matches found» — ? и * это маски.
alias bug='noglob bug' book='noglob book' ans='noglob ans' loot='noglob loot' memory='noglob memory' ask='noglob ask'

# FB3 (3): песочница после решения — дальше командой next. more здесь только напоминает, что
# ещё урок — слово new в убежище. Только в этом режиме: more с аргументами — пейджер.
if [[ -n $TERMIT_LINGER ]]; then
  unalias next more 2>/dev/null
  next() { _tr next }
  more() {
    if (( $# )) || [[ ! -t 0 ]]; then      # с аргументами или в конвейере — пейджер
      command more "$@"
    else
      _tr more
    fi
  }
fi

# FB5 п. 40: русская раскладка. Команда кириллицей («ды», «св») — подсказка «это ls», иначе
# обычное «command not found». _termit_layout_hint — отдельная функция: хаб (блок HUB-WORDS)
# зовёт её первой строкой своего command_not_found_handler, и обработчики склеиваются.
_termit_layout_hint() {
  [[ $1 == *[А-Яа-яЁё]* ]] || return 1
  _tr layout "$1"
}
command_not_found_handler() {
  _termit_layout_hint "$1" && return 127
  print -u2 -r -- "zsh: command not found: $1"
  return 127
}
# Esc, потом «.» в русской раскладке приходит как Esc, «ю» — то же «последнее слово»
bindkey '\eю' insert-last-word 2>/dev/null

# FB13 (FB5 п. 45 б): подсказчик привычек. Хуку нужно знать, набрана ли строка руками: ↑,
# поиск по истории, Esc+., Tab, вставка, Ctrl+Y и !-подстановка — уже не «перепечатал».
# zle-line-pre-redraw видит каждый виджет; 2+ знака разом не от self-insert (Tab, вставка,
# подсказка autosuggestions) — тоже не руками. Флаг: 0 — руками, 1 — нет, 2 — неизвестно
# (zle не работал); preexec пишет его с меткой команды в .termit/typed. Хуки zle — через
# add-zle-hook-widget: чужие (syntax-highlighting и т.п.) не сбиваются.
typeset -gi _tr_recall=2 _tr_blen=0
_tr_typed_init() { _tr_recall=0; _tr_blen=$#BUFFER }
_tr_typed_redraw() {
  [[ $LASTWIDGET == *(history|search|last-word|prev|paste|complet|autosuggest|yank|expand)* ]] &&
    _tr_recall=1
  (( $#BUFFER - _tr_blen >= 2 )) && [[ $LASTWIDGET != *self-insert* ]] && _tr_recall=1
  _tr_blen=$#BUFFER
}
_tr_typed_finish() {
  [[ $BUFFER == *'!'* || $BUFFER == '^'* ]] && _tr_recall=1
}
if autoload -Uz add-zle-hook-widget 2>/dev/null; then
  add-zle-hook-widget line-init _tr_typed_init 2>/dev/null
  add-zle-hook-widget line-pre-redraw _tr_typed_redraw 2>/dev/null
  add-zle-hook-widget line-finish _tr_typed_finish 2>/dev/null
fi

# Служебные команды не попадают в историю — иначе !! повторит task.
typeset -ga _tr_service=(task hint ans reset giveup skip quit bug loot memory ask keys ext book lesson)
[[ -n $TERMIT_LINGER ]] && _tr_service+=(next)
_tr_addhist() {
  local w=${${(z)1}[1]}
  (( ${_tr_service[(Ie)$w]} )) && return 1
  [[ -n $TERMIT_LINGER && ${1%%$'\n'} == more ]] && return 1
  return 0
}

zmodload zsh/datetime
_tr_preexec() {
  [[ -d $TERMIT_BOX/.termit ]] || return 0   # служебную папку удалили — хук сам об этом скажет
  # cat, sort и grep без файла ждут ввода с клавиатуры — новичку кажется, что всё зависло
  local -a _tr_w=(${(z)1})
  if { (( ${#_tr_w} == 1 )) && [[ $_tr_w[1] == (cat|sort|uniq|wc|head|tail|tr) ]] } ||
     { (( ${#_tr_w} == 2 )) && [[ $_tr_w[1] == grep ]] }; then
    print -r -- "(${_tr_w[1]} без файла ждёт ввода с клавиатуры — выйти: Ctrl+C)"
  fi
  if [[ $_tr_w[1] == ls ]] && _tr_home_empty; then
    print -r -- "(дом песочницы пуст — ls молчит. Назад, где был: cd -)"
  fi
  _tr_stamp=$EPOCHREALTIME
  print -r -- "$_tr_stamp"$'\t'"$PWD"$'\t'"${1//$'\n'/ }" >> $TERMIT_BOX/.termit/cmds.log
  print -r -- "$_tr_stamp"$'\t'"$_tr_recall" >| $TERMIT_BOX/.termit/typed
  _tr_recall=2
}
_tr_precmd() {
  local rc=$? ps="${pipestatus[*]}"
  # коды возврата команды из cmds.log (метка времени — та же): «до/после» засчитывает
  # утилиту, только если команда с ней отработала (I9)
  if [[ -n $_tr_stamp && -d $TERMIT_BOX/.termit ]]; then
    print -r -- "$_tr_stamp"$'\t'"$ps" >> $TERMIT_BOX/.termit/rc.log
  fi
  _tr_stamp=
  _tr precmd "$rc" "$PWD"
  if (( $? == 10 )); then
    setopt no_check_jobs                # выйти, даже если vim приостановлен через Ctrl+Z
    exit 0
  fi
}
zshaddhistory_functions=(_tr_addhist $zshaddhistory_functions)
preexec_functions=(_tr_preexec $preexec_functions)
precmd_functions=(_tr_precmd $precmd_functions _tr_unfzf_once)   # одноразовая — последней

if [[ -n $TERMIT_BARE ]]; then
  PROMPT='%1~ %# '
fi
# Своё приглашение игрока из деталей убежища — только здесь, поверх темы владельца.
# Настоящий ~/.zshrc игра не трогает. Значение задаёт родитель, не игрок.
[[ -n $TERMIT_PROMPT ]] && PROMPT=$TERMIT_PROMPT
[[ -n $TERMIT_RPROMPT ]] && RPROMPT=$TERMIT_RPROMPT
PROMPT="%F{yellow}[$TERMIT_LABEL]%f $PROMPT"
# FB3 (3) + FB5 (8): строки над приглашением — карточки доски убежища (текст задаёт родитель,
# строк может быть несколько). Текст — только для показа: % ! $ ` \ экранируем, чтобы тема
# владельца с prompt_subst или prompt_bang не раскрыла в нём ни переменную, ни команду.
if [[ -n $TERMIT_TIPS ]]; then
  _tr_tips=${TERMIT_TIPS//\%/%%}
  [[ -o prompt_bang ]] && _tr_tips=${_tr_tips//\!/!!}
  if [[ -o prompt_subst ]]; then
    _tr_tips=${_tr_tips//\\/\\\\}
    _tr_tips=${_tr_tips//\$/\\\$}
    _tr_tips=${_tr_tips//\`/\\\`}
  fi
  if [[ -n $NO_COLOR ]]; then
    PROMPT="$_tr_tips"$'\n'"$PROMPT"
  else
    PROMPT="%F{cyan}$_tr_tips%f"$'\n'"$PROMPT"
  fi
  unset _tr_tips
fi

# «Капкан»: поручение само запускает команду (например, vim) при старте.
if [[ -n $TERMIT_AUTORUN ]]; then
  print -r -- "$EPOCHREALTIME"$'\t'"$PWD"$'\t'"$TERMIT_AUTORUN" >> $TERMIT_BOX/.termit/cmds.log
  eval "$TERMIT_AUTORUN"
  unset TERMIT_AUTORUN
fi

# HUB-WORDS:START
# Слово убежища, набранное в задаче рана из убежища (хаб, спека 2.1):
# подсказка, как вернуться, вместо «command not found». Настоящие команды не трогаются.
# Список слов — hub.WORDS без команд задачи (hook.SERVICE: lesson, quit… остаются самими
# собой) и без зарезервированного слова case; полноту сверяет tests/test_hub.py.
if [[ -n $TERMIT_HUB ]]; then
  command_not_found_handler() {
    _termit_layout_hint "$1" && return 127
    case $1 in
      board|callsign|clear|coach|deck|diary|dossier|feedback|fence|help|home|hub|implants|inbox|intro|list|look|map|master|music|new|owl|palette|play|prompt|rehearse|report|run|shop|short|sound|stats|style|theme|train|update|wheels)
        print -r -- "$1 — слово убежища. quit — и ты в убежище, там набери $1."
        return 127 ;;
    esac
    print -u2 -r -- "zsh: command not found: $1"
    return 127
  }
fi
# HUB-WORDS:END
