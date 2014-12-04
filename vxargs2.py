#!/usr/bin/env python
# vxargs2
# kroemm01
"""
vxargs2 - ssh to multiple nodes in a cheeky way.

Usage:
vxargs2.py <filename>

keys :
    u   - increase concurrency in next command run
    d   - decrease concurrency in next command run
    tab - switch between list and command line
    esc - command mode (like in vi)
    q   - close vxargs2
"""

import urwid
import sys
import subprocess
import tempfile


# Load given file, parse to ignore comments.
def getListFromFile(f):
    hostlist = []
    for line in f:
        if line[0] != '#':
            if line.strip():
                hostlist.append([line.strip(), ''])
        elif hostlist and hostlist[-1][1] == '':
            hostlist[-1][1] = line.strip()[1:]
    return hostlist


# Each item is a widget with this functionality.
class ItemWidget (urwid.WidgetWrap):
    def __init__(self, id):
        self.title = urwid.Text(id)
        self.state = 'NORMAL'
        self.item = urwid.AttrWrap(self.title, self.state, 'focus')
        self.content = id
        self.__super.__init__(self.item)

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def set_state(self, state):
        self.state = state
        tmp = self.title.get_text()
        self.title.set_text((self.state, tmp[0]))

    def state(self):
        return self.state


# Header - this keeps status of shit
class HeaderWidget (urwid.WidgetWrap):
    def __init__(self, total, concurrency):
        self.total = total
        self.completed = 0
        self.progress = 0
        self.failed = 0
        self.running = 0
        self.concurrency = concurrency
        self.queued = self.total
        self.progress_bar = urwid.ProgressBar('pg normal', 'pg complete', 0, 100, 'pg smooth')
        self.status_bar = urwid.Text(('head', ''), align='right')

        self.update()
        self.header_col = urwid.Columns([('fixed', 50, self.progress_bar), self.status_bar], 0)
        urwid.WidgetWrap.__init__(self, self.header_col)

    def tick(self, state):
        if state == 'FAIL':
            self.failed += 1
        elif state == 'OK':
            self.completed += 1
        elif state == 'RUN':
            self.running += 1
        else:
            self.completed = 0
        self.progress = (self.completed * 100) / self.total
        self.queued = self.total - ( self.completed + self.failed )
        self.update()

    def setitall(self, completed, failed):
        self.completed = completed
        self.failed = failed
        self.progress = ((self.completed + self.failed) * 100) / self.total
        self.queued = self.total - (self.completed + self.failed)
        self.update()

    def update(self):
        self.status_bar.set_text(('head', '  Total: %d    Completed: %d/%d    Queued: %d    Concurency: %d' % (self.total, self.completed, self.failed, self.queued, self.concurrency)))
        self.progress_bar.set_completion(self.progress)

    def progress(self):
        return self.progress


# Output from files goes here
class OutputBody (urwid.WidgetWrap):
    def __init__(self):
        self.body = urwid.Text("none")
        urwid.WidgetWrap.__init__(self, self.body)

    def load_file(self, filename):
        try:
            f = open(filename)
            self.body.set_text(f.read())
        except:
            self.body.set_text("no output yet, be patient")


# This is our command line.
class CommandLine(urwid.Edit):
    __metaclass__ = urwid.signals.MetaSignals
    signals = ['done']

    def keypress(self, size, key):
        if key == 'enter':
            urwid.emit_signal(self, 'done', self.get_edit_text())
            return
        elif key == 'esc':
            urwid.emit_signal(self, 'done', None)
            return
        elif key == 'tab':
            urwid.emit_signal(self, 'done', None)
            return
        urwid.Edit.keypress(self, size, key)


#####
#
#####
class MyApp(object):

    def __init__(self):

        palette = [
            ('body', 'white', '', 'standout'),
            ('NORMAL', 'white', 'black', 'standout'),
            ('OK', 'white', 'dark green', 'standout'),
            ('FAIL', 'white', 'dark red', 'standout'),
            ('RUNNING', 'black', 'white', 'standout'),
            ('focus', 'light gray', 'dark red', 'standout'),
            ('head', 'white', 'dark blue'),
            ('pg normal',    'white',      'black', 'standout'),
            ('pg complete',  'white',      'dark magenta'),
            ('pg smooth',     'dark magenta', 'black')

            ]

        self.tempdir = tempfile.mkdtemp(prefix="vxargs2.") + '/'
        print "Output directory for this session : " + self.tempdir
        self.items = []
        self.concurrency = 1

        # LOAD FILE
        try:
            f = open(sys.argv[1])
        except:
            sys.stderr.write(__doc__)
            return

        self.ItemsList = getListFromFile(f)
        for ii in self.ItemsList:
            item = ItemWidget(ii)
            self.items.append(item)

        # MID
        self.window = OutputBody()
        fill = urwid.Filler(self.window, 'top')

        # HEAD
        self.header = HeaderWidget(len(self.items), self.concurrency)

        walker = urwid.SimpleListWalker(self.items)
        self.listbox = urwid.ListBox(walker)
        col = urwid.Columns([fill, ('fixed', 9, self.listbox)], 1)
        self.view = urwid.Frame(urwid.AttrWrap(col, 'body'), header=self.header)
        self.foot = CommandLine(sys.argv[1] + ':~$ ')
        self.view.set_footer(self.foot)
        self.view.set_focus('footer')
        urwid.connect_signal(self.foot, 'done', self.edit_done)
        self.loop = urwid.MainLoop(self.view, palette, unhandled_input=self.keystroke)
        urwid.connect_signal(walker, 'modified', self.update)
        self.loop.set_alarm_in(1, self.update_listbox)
        self.loop.run()

    def update_listbox(self, loop=None, user_data=None):
        nodesok = 0
        nodesfail = 0
        for i, node in enumerate(self.ItemsList):
            outfile = self.tempdir + str(node[0]) + '.out'
            statusfile = self.tempdir + str(node[0]) + '.status'
            try:
                open(outfile, 'r')
                try:
                    sfd = open(statusfile, 'r')
                    for line in sfd:
                        if line == '0':
                            self.items[i].set_state('OK')
                            nodesok += 1
                        else:
                            self.items[i].set_state('FAIL')
                            nodesfail += 1
                except:
                    self.items[i].set_state('RUNNING')
            except:
                self.items[i].set_state('NORMAL')
        self.header.setitall(nodesok, nodesfail)
        self.loop.set_alarm_in(1, self.update_listbox)

    # walker update
    def update(self):
        focus = self.listbox.get_focus()[0].content
        self.window.load_file(self.tempdir + focus[0] + '.out')

    # key binding in main view
    def keystroke(self, input):
        if input in ('q', 'Q'):
            raise urwid.ExitMainLoop()

        if input is 'enter':
            focus = self.listbox.get_focus()[0].content
            self.window.load_file(self.tempdir + focus[0] + '.out')

        if input is 'u':
            self.concurrency += 1
            self.header.concurrency += 1
            self.header.update()

        if input is 'd':
            self.concurrency -= 1
            self.header.concurrency -= 1
            self.header.update()

        if input is 'tab':
            self.view.set_focus('footer')

    # when you hit enter, this shit happens
    def edit_done(self, content):
        self.view.set_focus('body')
        urwid.disconnect_signal(self, self.foot, 'done', self.edit_done)
        if content:
            subprocess.Popen(["vxargs.py", "-t", "300", "-a", sys.argv[1], "-P", str(self.concurrency), "-y", "-p", "-o", self.tempdir, "ssh", "{}", content], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.view.set_focus('body')


if __name__ == '__main__':
    MyApp()
