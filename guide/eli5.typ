// ELI5 guide: RPLIDAR A1 on the Zybo Z7-10. Build (from this folder):
//   typst compile --root .. eli5.typ Lidar_ELI5_Guide.pdf
// Reuses figs/*.svg made by figs.py and ../media photos. Numbers come from the full guide (check.py).
#set document(title: "Lidar on an FPGA, Explained Simply", author: "Muhammad Refansa")
#set page(paper: "a4", margin: (x: 2.4cm, y: 2.3cm), numbering: "1", number-align: center)
#set text(font: "New Computer Modern", size: 11pt, fill: black, lang: "en")
#set par(justify: true, leading: 0.7em, spacing: 1em)
#set heading(numbering: "1.")
#show heading.where(level: 1): it => {
  v(1.1em, weak: true)
  block(text(size: 16pt, weight: "bold", it))
  v(0.4em)
}
#show heading.where(level: 2): it => block(above: 1.2em, below: 0.6em, text(size: 12pt, weight: "bold", it))
#show raw: set text(size: 9pt)
#show figure.caption: set text(size: 9.5pt)
#show figure: set block(above: 1.2em, below: 1.2em)
#set table(stroke: none, inset: (x: 6pt, y: 4pt))
#show table: set par(justify: false)

#let hr = table.hline(stroke: 0.8pt)
#let thin = table.hline(stroke: 0.4pt)

#let imagine(body) = block(width: 100%, stroke: (left: 2.5pt + black, rest: 0.5pt + black), inset: (left: 10pt, rest: 8pt), above: 1.1em, below: 1.1em, breakable: false)[
  #text(weight: "bold", size: 9.5pt, smallcaps[Imagine this]) \
  #body
]
#let real(body) = block(width: 100%, fill: luma(242), stroke: 0.5pt + black, inset: 8pt, above: 1.1em, below: 1.1em, breakable: false)[
  #text(weight: "bold", size: 9.5pt, smallcaps[The grown-up word]) \
  #body
]
#let fig(file, cap, w: 100%) = figure(image("figs/" + file + ".svg", width: w), caption: cap)
#let photo(file, cap, w: 100%) = figure(image("../media/" + file, width: w), caption: cap)
#let node(body, w: auto, fill: white) = rect(width: w, inset: 7pt, stroke: 0.8pt + black, fill: fill, align(center, body))

// ---------------------------------------------------------------- title
#align(center)[
  #v(1.6cm)
  #text(size: 23pt, weight: "bold")[Lidar on an FPGA]
  #v(0.3em)
  #text(size: 14pt)[...explained like you are five]
  #v(0.9em)
  #text(size: 10.5pt)[Muhammad Refansa · FPGA study group · October 2026]
  #v(1.2em)
]

#block(inset: (x: 1.2cm))[
  #set text(size: 10.5pt)
  This is the short, friendly version of the full guide. It has no register tables and almost no code. It answers one question: *what is going on inside this project, and why?* If you can follow this, you can follow the long guide, which has all the details, code and build steps. Every number here was measured on the real board or checked with a script, the same as in the long guide.
]

#v(0.6cm)

= What did we build?

A *lidar* is a small machine that measures distances with a laser. Ours is an RPLIDAR A1. It spins around about 6 to 7 times every second. It fires its laser about 2000 times every second. Each time, it tells us: "In *this* direction, there is something *this* far away."

#imagine[
  A lighthouse that spins and, instead of shining a beam for ships, uses a very fast measuring tape. It shouts "direction, distance!" two thousand times a second.
]

We connected it to a *Zybo Z7-10*, a small board with an *FPGA* chip on it. The board does four jobs:

+ *Wake the lidar up* and check that it is healthy.
+ *Spin its motor* at a speed we choose.
+ *Listen* to the stream of "direction, distance" messages and find where each full turn starts.
+ *Report*: print one line per turn, light some LEDs, and (if we want) send the whole picture to a PC that draws it.

#photo("hardware_setup.jpg", [The real setup. The lidar (bottom) is wired to the Zybo through a breadboard. Power for the lidar comes from a separate USB source, because the motor is hungry.], w: 34%)

#photo("zybo_direct_plot.png", [What the board hears, drawn by a PC. The red triangle is the lidar. Each dot is one "direction, distance" message. The rings show distance.], w: 42%)

That picture is the whole point. Everything else in this guide is about how those dots travel from the spinning sensor into the board *without getting lost or mixed up*.

= Meet the cast

== The chip is a small house with two people in it

The big chip on the Zybo is called a *Zynq*. It has two parts, and it helps to think of them as two different people:

#figure(
  grid(columns: (1fr, auto, 1fr), column-gutter: 6pt, align: horizon,
    node[*The manager* \ #text(size: 9.5pt)[A normal small computer. Always there. Runs our C program. Reads, decides, prints.]],
    align(center)[#text(size: 18pt)[$arrow.l.r$] \ #text(size: 9pt)[the hallway]],
    node[*The workshop* \ #text(size: 9.5pt)[An empty room full of Lego bricks. We choose which bricks to put in: a serial port, a motor controller.]],
  ),
  caption: [Inside the Zynq. The manager and the workshop talk through a hallway.],
)

#real[
  The manager is the *PS* (processing system, an ARM processor). The workshop is the *PL* (programmable logic, the "FPGA" part). The hallway is called *AXI*.
]

== Mailboxes with house numbers

How does the manager talk to a brick in the workshop? Every brick has a few *mailboxes*, and every mailbox has an address, like a house number. The manager writes a note into mailbox `0x41200000` and the motor controller changes its speed. The manager reads mailbox `0x42C00008` and learns whether a message has arrived. In C, this is only two actions: _read a mailbox_ and _write a mailbox_.

#real[Mailboxes are called *registers*. This idea is called *memory-mapped* hardware.]

== The one-lane road: UART

The lidar sends its messages to the board over a *UART*. It is a very simple road: one wire, one lane, and the bytes go one after another. There is no clock wire. Instead, both sides agree on a speed before they start (here 115 200 bits per second). One byte takes 10 bits, so the road carries at most *11 520 bytes per second*, and not a single one more.

Two golden rules for this road: the sender's TX wire goes to the receiver's *RX* wire (a "talk" plug into a "listen" socket), and both sides must share a ground wire.

== Flicking a switch very fast: PWM

How do you make a motor go "a bit slower" if you only have an on/off switch? You flick the switch on and off *very* fast (24 000 times a second). The motor cannot follow each flick. It just feels the average. If the switch is on half the time, the motor feels "half power".

#fig("pwm", [Three settings. The pattern repeats very fast. Only the fraction of time spent "on" changes.], w: 70%)

This is the one thing we built ourselves in the workshop. It is a counter that counts around a loop, plus one question: "Is the counter below my limit? Then switch on." About 15 lines of Verilog.

#real[This trick is *PWM* (pulse-width modulation). The fraction of "on" time is the *duty cycle*. Ours is an 8-bit number from 0 to 255. We use 120, which is on about 47% of the time.]

== A manager with no helpers: bare-metal

Our C program has no Windows or Linux under it. It is a single person doing a single endless loop: check this, check that, check this, check that. Nobody else can step in while it is busy. This one fact explains almost every problem we had, as you will see.

= How the lidar talks

== One message = one postcard

The lidar sends us tiny messages. Each is exactly *5 bytes*, like a postcard with a fixed set of boxes to fill in:

#figure(
  grid(columns: (1.1fr, 1fr, 1.2fr, 1.4fr), column-gutter: 0pt,
    node(fill: luma(225))[#text(size: 9.5pt)[*Check marks* \ "I am a real postcard"]],
    node[#text(size: 9.5pt)[*Quality* \ "How sure am I?"]],
    node[#text(size: 9.5pt)[*Direction* \ "Which way, 0 to 360°"]],
    node[#text(size: 9.5pt)[*Distance* \ "How far, in millimetres"]],
  ),
  caption: [One postcard (a "node" in the long guide). Five bytes, four things to read.],
)

About 1980 postcards arrive every second, forever, with *no gap and no marker* between them. They are just a long river of bytes.

== Two small tricks that make the river readable

*Check marks.* Each postcard contains two special bits that are always opposites, plus one bit that is always 1. If a postcard breaks these rules, we know we are reading it wrong. It is like every postcard having a stamp in the corner: if the stamp is missing, we are holding it wrong.

*"New turn" flag.* The lidar never says "I finished a turn". Instead, the first postcard of each new turn carries a flag. So one full turn is simply *everything between two flagged postcards*.

#fig("polar", [One turn, sorted by direction: a far wall, a close object to one side, something in front.], w: 50%)

= Not losing any mail

This is the part that surprised us most.

== The tiny mailbox that overflows

The serial brick in the workshop has a mailbox that holds only *16 bytes*. The lidar fills it at about one byte every 100 µs. How long until it is full? About *1.4 milliseconds*. If the manager does not empty it within that time, the next byte falls on the floor, and nobody tells us.

#imagine[
  A mail slot that holds 16 letters, and a postman who delivers a new letter every tenth of a millisecond. If you leave to make a cup of tea, the floor fills with letters.
]

Now think about the manager *printing a line of text*. The normal print command waits for the screen's own slow road to take every letter. A 90-letter line takes about 8 milliseconds. During those 8 milliseconds, the manager is not looking at the mail slot. Over 60 letters arrive. Only 16 fit. Every single `print` would wreck a big part of a turn.

== The fix: a notepad

We stopped printing directly. Now, when the program wants to print, it just *writes the text on a big notepad* (a 4 000-letter array in memory) and moves on instantly. Every pass around the loop, it also sends a few letters from the notepad to the screen, as many as the screen will accept right now, and moves on again. The mail slot is emptied on every pass.

#fig("fifo", [Top: a normal print stops the manager, so the mail slot overflows. Bottom: printing only writes to the notepad, so the mail slot is emptied on every pass.])

The notepad is a *circular* one. A "write finger" and a "read finger" chase each other around it like runners on a circular track. When the write finger reaches the end, it jumps back to the start.

And what if the notepad is full? Then the *screen* loses text, never the lidar. Losing a few letters of console text is harmless. Losing lidar data is not. In this project the sensor always matters more than the screen.

#real[The notepad is a *ring buffer* (or circular buffer). The mail slot is the UART's *FIFO*. A byte lost because the FIFO was full is an *overrun*.]

== Proof, not hope

The board counts lost bytes and prints the count on every line (`ovr`). In our run, it stayed at *0* for hundreds of turns. "It does not lose data" only counts if the program can show it.

= Finding where a postcard starts

Suppose we start listening in the middle of a postcard, or one byte gets lost. Now every group of five bytes is shifted, and every "postcard" we read is nonsense.

== Slide a window

The parser looks at the last five bytes through a little window and asks: "Do the check marks hold? Is the direction a real direction (below 360°)?" If not, it throws away *one* byte, slides the window along, and tries again. When the alignment is right, the check marks pass again and again.

== One good window is not enough

How easily can *random noise* pass for a good postcard? We tested it on 200 000 random bytes:

#figure(
  table(columns: (1fr, auto), align: (left, right), hr,
    [*Check*], [*Noise that fools it*], hr,
    [Check marks only], [1 in 4], thin,
    [Check marks and a real direction], [1 in 5.7], thin,
    [... three windows in a row], [about 1 in 180], hr,
  ),
  caption: [Measured with `check.py`.],
)

One in four is far too weak: noise would fool us all the time. So the parser waits until *three* good postcards in a row line up before it believes the alignment. It also ignores any "turn" with fewer than 100 points. With these rules, 100 kB of pure noise gives *zero* fake turns.

#imagine[
  Recognising a song. One note fits a thousand songs. Three notes in the right order fit almost none. The parser wants three notes before it says "I know this tune."
]

== Building one turn

Each accepted postcard goes into a table with *360 slots, one per degree*. If two postcards land in the same slot, we keep the *closer* one, because for safety the nearest obstacle matters most. When the next "new turn" flag arrives, the turn is finished. The first turn after start-up is always thrown away, because we joined it halfway through.

From the table the program gets one useful number: *how close is the nearest thing in front of us?* If it is closer than 1 metre, one LED turns on. If it is closer than 30 cm, another one does.

= How we know it works

== Never test two new things at once

If you connect two new things and nothing works, you cannot tell which one is broken. So we proved each half *on its own* first, then joined them one step at a time:

#figure(
  table(columns: (auto, 1fr), align: (center, left), hr,
    [*1*], [Simulated the motor controller on the PC: the maths is right.], thin,
    [*2*], [Fed the parser a fake stream on the PC: the parser logic is right.], thin,
    [*3*], [Plugged the lidar into a laptop: the sensor works, and we understand it.], thin,
    [*4*], [Connected the board's TX pin to its own RX pin (a loopback): the board's serial port works.], thin,
    [*5*], [A fake lidar on the laptop, through the board: the board's software works.], thin,
    [*6*], [The real lidar through the laptop, through the board: real data works.], thin,
    [*7*], [The real lidar wired straight to the board: the whole system.], hr,
  ),
  caption: [Seven steps. Each changes exactly one thing from the step before.],
)

When step 7 first failed, steps 1 to 6 had already shown the board, the parser and the sensor were fine. So the problem had to be in the wires between them (it was, see below).

== A watchdog that barks

What if a cable falls out while the motor is running? The program remembers the time of the last good postcard. If more than 1.5 seconds pass with none, it prints a message and restarts the whole start-up conversation with the lidar. It is like a guard dog: every good postcard feeds it, and if the food stops, it barks.

= What we saw

With the lidar wired straight to the board, the console prints one line per turn:

#photo("zybo_direct_console.png", [Console output. About 7 turns a second, about 280 points per turn, and `ovr 0`: no lost bytes.], w: 72%)

We changed the motor speed from slow to fast and wrote down what happened:

#fig("sweep", [A faster motor gives more turns per second but fewer points in each turn. Above about duty 240 the motor cannot go faster.], w: 76%)

The interesting part: *turns per second × points per turn is always about 1980*. The lidar fires its laser at a fixed rate, whatever the motor does.

#imagine[
  A sprinkler that always sprays the same number of drops per second. If you spin it faster, the drops spread over more circles, so each circle gets fewer drops. If you spin it slower, each circle is dense. You choose: *fresh picture* (fast) or *detailed picture* (slow).
]

We chose a middle setting: *6.35 turns per second* and *312 points per turn*, about 1.15° between neighbouring points.

One thing we did *not* prove: why the rate is exactly 1980. It could be the sensor's own limit, or it could be the speed limit of the 115 200-baud road (at most about 2300 postcards per second), which is close. We say so rather than guess.

= What went wrong

Real projects are mostly debugging. None of the problems below were mistakes in our clever code. They were timers, wires, paths and tools.

#figure(
  table(columns: (1fr, 1.7fr), align: (left, left), inset: (x: 6pt, y: 5pt), hr,
    [*What we saw*], [*What it really was*], hr,
    [The program froze at "Motor on, waiting 2 s".], [The board's timer only starts the first time something calls `usleep`. Nobody had, so "wait 2 seconds" never ended. Fix: one line at the top of `main`.], thin,
    [The board heard nothing from the lidar.], [Two outputs were wired to the same breadboard row. Two things shouting on one wire cancel each other out.], thin,
    [Still silent, though the wiring matched our table.], [Our colour table of the lidar cable had three signals on the wrong pins. The power wires were right. Lesson: check against the real connector's printed labels.], thin,
    [Fake "turns" appeared out of noise.], [The 2-bit check passes noise 1 time in 4. Lesson: measure the false-alarm rate, then add the 3-in-a-row rule.], thin,
    [The software tool could not build.], [A space in the folder name. We built in `D:\lidar_build` instead.], hr,
  ),
  caption: [Five bugs and what they taught us.],
)

The cure was always the same: *make the problem smaller until only one thing can be blamed.* That is exactly what the test ladder does.

= Words you now know

#figure(
  table(columns: (auto, 1fr), align: (left, left), hr,
    [*Lidar*], [A spinning laser tape measure. Reports (direction, distance) about 2000 times a second.], thin,
    [*Zynq PS / PL*], [The manager (an ARM computer) / the workshop (the FPGA part) of one chip.], thin,
    [*AXI*], [The hallway between the manager and the workshop.], thin,
    [*Register*], [A mailbox with an address that the manager can read or write.], thin,
    [*UART*], [A one-wire road for sending bytes at an agreed speed.], thin,
    [*PWM*], [Flicking a switch very fast so a motor feels an "average" power.], thin,
    [*Bare-metal*], [Software with no operating system: one person, one endless loop.], thin,
    [*FIFO / overrun*], [A small mail slot / a letter that fell on the floor because the slot was full.], thin,
    [*Ring buffer*], [A circular notepad that lets slow printing and fast listening coexist.], thin,
    [*Parser*], [The code that finds where each postcard starts and builds a turn from them.], thin,
    [*Watchdog*], [A timer that restarts things if the good news stops coming.], hr,
  ),
)

= Where to go next

If this made sense, the long guide (`Lidar_on_an_FPGA_Guide.pdf`, same folder) goes deeper, in this order:

- *Chapters 1 and 2:* the same cast, with real addresses, a register table and the Zynq in detail.
- *Chapters 3 and 8:* the exact bits of a postcard and the parser, with a worked example you can decode by hand.
- *Chapter 4:* the Verilog motor controller, line by line.
- *Chapters 5 to 7:* the C program, the timer story, the ring buffer and the watchdog.
- *Chapter 10:* build and run everything yourself, step by step.
- *Chapter 13:* exercises, from pencil-and-paper to changing the hardware.

#imagine[
  The best habit in this whole project was not clever code. It was *testing each half alone before joining them.* Whenever something fails, ask: "Which half is the problem?"
]
