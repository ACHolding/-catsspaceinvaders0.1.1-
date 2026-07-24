#!/usr/bin/env python3
"""
AC's Space Invaders Py Port 0.1
Famicom-style fixed shooter
60 FPS | Single-file | Pure Pygame | Procedural 8-bit graphics and audio
Python 3.14 compatible
"""

from array import array
import math
import random

try:
    import pygame
except ImportError as exc:
    raise SystemExit(
        "AC's Space Invaders Py Port 0.1 needs pygame-ce. "
        "Install it with: python3 -m pip install pygame-ce"
    ) from exc

# =============================================================================
# CONSTANTS
# =============================================================================
WIDTH, HEIGHT = 800, 600
FPS = 60
TITLE = "AC's Space Invaders Py Port 0.1"

# Restricted Famicom/NES-inspired palette
BLACK = (0, 0, 0)
DEEP_SPACE = BLACK
WHITE = (236, 238, 236)
CYAN = (60, 188, 252)
PINK = (236, 88, 180)
ORANGE = (248, 184, 0)
YELLOW = (248, 216, 0)
RED = (228, 0, 88)
GREEN = (88, 216, 84)
PURPLE = (104, 68, 252)
BLUE = (0, 120, 248)
GRAY = (88, 88, 88)


def draw_pixel_pattern(surface, pattern, x, y, pixel_size, color):
    """Draw an arcade sprite from a tuple of 0/1 strings."""
    for row_index, row in enumerate(pattern):
        for column_index, value in enumerate(row):
            if value == "1":
                pygame.draw.rect(
                    surface,
                    color,
                    (
                        int(x + column_index * pixel_size),
                        int(y + row_index * pixel_size),
                        pixel_size,
                        pixel_size,
                    ),
                )


class PixelFont:
    """Bundled bitmap-font wrapper rendered with crisp integer-sized pixels."""

    def __init__(self, target_size, bold=False, pixel_scale=3):
        base_size = max(5, round(target_size / pixel_scale))
        self.font = pygame.font.Font(None, base_size)
        self.font.set_bold(bold)
        self.pixel_scale = pixel_scale

    def render(self, text, _antialias, color):
        glyphs = self.font.render(str(text), False, color)
        width = max(1, glyphs.get_width() * self.pixel_scale)
        height = max(1, glyphs.get_height() * self.pixel_scale)
        return pygame.transform.scale(glyphs, (width, height))


# =============================================================================
# PROCEDURAL SFX (single-file: no external sound assets required)
# =============================================================================
class AudioManager:
    """Synthesize Famicom-style pulse, triangle, and noise audio in memory."""

    SAMPLE_RATE = 22050

    def __init__(self):
        self.enabled = False
        self.muted = False
        self.sounds = {}

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(
                    frequency=self.SAMPLE_RATE,
                    size=-16,
                    channels=2,
                    buffer=512,
                )
            mixer_rate, mixer_format, mixer_channels = pygame.mixer.get_init()
            if mixer_format != -16 or mixer_channels != 2:
                return
            self.SAMPLE_RATE = mixer_rate
            pygame.mixer.set_num_channels(8)
            self.sounds = {
                "shoot": self._make_sweep(1320, 260, 0.10, 0.18, "pulse12"),
                "hit": self._make_sweep(460, 90, 0.15, 0.22, "noise"),
                "hurt": self._make_sweep(260, 48, 0.38, 0.24, "triangle"),
                "ufo": self._make_arpeggio((72, 76, 79, 84), 0.055, 0.18),
                "wave": self._make_arpeggio((60, 64, 67, 72, 76), 0.085, 0.20),
                "select": self._make_arpeggio((72, 79), 0.05, 0.14),
                "march": self._make_sweep(118, 94, 0.055, 0.08, "pulse25"),
            }
            self.enabled = True
        except (pygame.error, ValueError, TypeError):
            self.enabled = False

    @staticmethod
    def _midi_frequency(note):
        return 440.0 * (2.0 ** ((note - 69) / 12.0))

    @staticmethod
    def _wave_sample(phase, wave, rng):
        cycle = phase % 1.0
        if wave == "pulse12":
            return 1.0 if cycle < 0.125 else -1.0
        if wave == "pulse25":
            return 1.0 if cycle < 0.25 else -1.0
        if wave == "pulse50":
            return 1.0 if cycle < 0.5 else -1.0
        if wave == "triangle":
            return 1.0 - 4.0 * abs(cycle - 0.5)
        return rng.uniform(-1.0, 1.0)

    def _make_sweep(self, start_hz, end_hz, duration, volume, wave):
        count = max(1, int(self.SAMPLE_RATE * duration))
        samples = array("h")
        rng = random.Random(811)
        for i in range(count):
            progress = i / count
            frequency = start_hz + (end_hz - start_hz) * progress
            phase = frequency * i / self.SAMPLE_RATE
            envelope = min(1.0, i / max(1, int(self.SAMPLE_RATE * 0.006)))
            envelope *= max(0.0, 1.0 - progress ** 2)
            value = int(
                32767
                * volume
                * envelope
                * self._wave_sample(phase, wave, rng)
            )
            samples.extend((value, value))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _make_arpeggio(self, notes, step_duration, volume):
        step_samples = max(1, int(self.SAMPLE_RATE * step_duration))
        samples = array("h")
        rng = random.Random(4242)
        total = step_samples * len(notes)
        for i in range(total):
            note_index = min(len(notes) - 1, i // step_samples)
            position = (i % step_samples) / step_samples
            frequency = self._midi_frequency(notes[note_index])
            envelope = min(1.0, position * 12.0) * max(0.0, 1.0 - position)
            phase = frequency * i / self.SAMPLE_RATE
            value = int(
                32767
                * volume
                * envelope
                * self._wave_sample(phase, "pulse25", rng)
            )
            samples.extend((value, value))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def play(self, name):
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted


# =============================================================================
# PARTICLE SYSTEM (juice)
# =============================================================================
class Particle:
    def __init__(self, x, y, color, life=30, size=3):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.life = life
        self.max_life = life
        self.size = float(size)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1.2, 4.5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 1.0  # slight upward bias
        self.gravity = 0.08

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.life -= 1
        self.size = max(0.8, self.size * (self.life / self.max_life))

    def draw(self, surface, offset=(0, 0)):
        if self.life <= 0:
            return
        pixel_size = max(2, int(self.size))
        pygame.draw.rect(
            surface,
            self.color,
            (
                int(self.x + offset[0]) - pixel_size // 2,
                int(self.y + offset[1]) - pixel_size // 2,
                pixel_size,
                pixel_size,
            ),
        )

    def is_alive(self):
        return self.life > 0


def spawn_explosion(particles, x, y, base_color, count=14):
    for _ in range(count):
        color = random.choice((base_color, WHITE, YELLOW, RED))
        particles.append(
            Particle(
                x,
                y,
                color,
                life=random.randint(18, 40),
                size=random.choice((2, 3, 4, 5)),
            )
        )


# =============================================================================
# BULLET
# =============================================================================
class Bullet:
    def __init__(self, x, y, speed=-9, color=CYAN, radius=5, is_player=True):
        self.x = float(x)
        self.y = float(y)
        self.speed = speed
        self.color = color
        self.radius = radius
        self.is_player = is_player
        self.active = True

    def update(self):
        self.y += self.speed
        if self.y < -30 or self.y > HEIGHT + 30:
            self.active = False

    def draw(self, surface, offset=(0, 0)):
        if not self.active:
            return
        cx = int(self.x + offset[0])
        cy = int(self.y + offset[1])
        core = (
            min(255, self.color[0] + 70),
            min(255, self.color[1] + 70),
            min(255, self.color[2] + 70),
        )
        if self.is_player:
            pygame.draw.rect(surface, self.color, (cx - 2, cy - 7, 4, 14))
            pygame.draw.rect(surface, core, (cx - 1, cy - 6, 2, 12))
        else:
            phase = (int(self.y) // 5) % 2
            points = [
                (cx - 3 if phase == 0 else cx + 3, cy - 8),
                (cx + 3 if phase == 0 else cx - 3, cy - 3),
                (cx - 3 if phase == 0 else cx + 3, cy + 2),
                (cx + 3 if phase == 0 else cx - 3, cy + 7),
            ]
            pygame.draw.lines(surface, self.color, False, points, 3)

    def get_rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius, self.radius * 2, self.radius * 2)


# =============================================================================
# PLAYER CANNON
# =============================================================================
class Player:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.width = 48
        self.height = 28
        self.speed = 6.5
        self.cooldown = 0
        self.cooldown_max = 18
        self.lives = 3
        self.invincible = 0
        self.bullets = []
        self.alive = True

    def update(self, keys):
        if not self.alive:
            return False
        fired = False
        # Movement
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.x -= self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.x += self.speed
        self.x = max(self.width // 2 + 8, min(WIDTH - self.width // 2 - 8, self.x))

        if self.cooldown > 0:
            self.cooldown -= 1
        if self.invincible > 0:
            self.invincible -= 1

        # Shoot (max 2 active player bullets)
        active = sum(1 for b in self.bullets if b.active and b.is_player)
        if (keys[pygame.K_SPACE] or keys[pygame.K_UP]) and self.cooldown <= 0 and active < 2:
            self.bullets.append(Bullet(self.x, self.y - self.height // 2 - 6, speed=-10, color=GREEN, radius=3))
            self.cooldown = self.cooldown_max
            fired = True

        for b in self.bullets:
            b.update()
        self.bullets = [b for b in self.bullets if b.active]
        return fired

    def hit(self):
        if self.invincible <= 0 and self.alive:
            self.lives -= 1
            self.invincible = 90
            if self.lives <= 0:
                self.alive = False
            return True
        return False

    def draw(self, surface, offset=(0, 0)):
        if not self.alive:
            return
        # Flicker when invincible
        if self.invincible > 0 and (self.invincible // 3) % 2 == 0:
            return

        cx = int(self.x + offset[0])
        cy = int(self.y + offset[1])

        # Classic stepped laser cannon silhouette.
        pygame.draw.rect(surface, GREEN, (cx - 24, cy + 6, 48, 8))
        pygame.draw.rect(surface, GREEN, (cx - 19, cy - 2, 38, 10))
        pygame.draw.rect(surface, GREEN, (cx - 10, cy - 8, 20, 8))
        pygame.draw.rect(surface, GREEN, (cx - 3, cy - 14, 6, 8))
        pygame.draw.rect(surface, WHITE, (cx - 1, cy - 13, 2, 7))

        for b in self.bullets:
            b.draw(surface, offset)

    def get_rect(self):
        return pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)


# =============================================================================
# CLASSIC PIXEL INVADER
# =============================================================================
class Invader:
    SPRITES = (
        (
            (
                "00100000100",
                "00010001000",
                "00111111100",
                "01101110110",
                "11111111111",
                "10111111101",
                "10100000101",
                "00011011000",
            ),
            (
                "00100000100",
                "10010001001",
                "10111111101",
                "11101110111",
                "11111111111",
                "01111111110",
                "00100000100",
                "01000000010",
            ),
        ),
        (
            (
                "00011011000",
                "00111111100",
                "01111111110",
                "11011011011",
                "11111111111",
                "00100100100",
                "01011011010",
                "10100000101",
            ),
            (
                "00011011000",
                "10111111101",
                "11111111111",
                "11011011011",
                "11111111111",
                "01011011010",
                "10000000001",
                "01000000010",
            ),
        ),
        (
            (
                "00001110000",
                "00111111100",
                "01111111110",
                "11101110111",
                "11111111111",
                "00110001100",
                "01101110110",
                "11011011011",
            ),
            (
                "00001110000",
                "00111111100",
                "01111111110",
                "11101110111",
                "11111111111",
                "00011011000",
                "00100100100",
                "01000000010",
            ),
        ),
    )

    def __init__(self, x, y, row, col, color, points):
        self.x = float(x)
        self.y = float(y)
        self.row = row
        self.col = col
        self.width = 44
        self.height = 32
        self.color = color
        self.points = points
        self.alive = True
        self.frame = 0

    def draw(self, surface, offset=(0, 0), anim_frame=0):
        if not self.alive:
            return
        cx = int(self.x + offset[0])
        cy = int(self.y + offset[1])
        sprite_type = 0 if self.row == 0 else 1 if self.row < 3 else 2
        pattern = self.SPRITES[sprite_type][anim_frame % 2]
        draw_pixel_pattern(
            surface,
            pattern,
            cx - self.width // 2,
            cy - self.height // 2,
            4,
            self.color,
        )

    def get_rect(self):
        return pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)


# =============================================================================
# SWARM
# =============================================================================
class Swarm:
    def __init__(self, start_y=70, wave=1):
        self.invaders = []
        self.direction = 1
        self.drop_amount = 16
        self.move_timer = 0
        self.move_interval = max(12, 36 - wave * 3)
        self.did_step = False
        self.anim_timer = 0
        self.anim_frame = 0
        self.bullets = []
        self.shoot_cooldown = 40
        self.wave = wave
        self.create_grid(start_y)
        self.total_start = len([i for i in self.invaders if i.alive])

    def create_grid(self, start_y):
        self.invaders = []
        colors = [
            RED,
            WHITE,
            WHITE,
            GREEN,
            GREEN,
        ]
        points = [30, 20, 20, 10, 10]
        rows, cols = 5, 11
        start_x = 70
        spacing_x = 56
        spacing_y = 40
        for r in range(rows):
            for c in range(cols):
                x = start_x + c * spacing_x
                y = start_y + r * spacing_y
                self.invaders.append(Invader(x, y, r, c, colors[r], points[r]))

    def alive_count(self):
        return sum(1 for inv in self.invaders if inv.alive)

    def get_alive(self):
        return [inv for inv in self.invaders if inv.alive]

    def update(self):
        self.did_step = False
        self.anim_timer += 1
        if self.anim_timer >= 18:
            self.anim_timer = 0
            self.anim_frame = 1 - self.anim_frame

        alive = self.get_alive()
        remaining = len(alive)
        if remaining == 0:
            return "cleared"

        # Classic speed-up
        self.move_interval = max(6, 34 - (self.total_start - remaining) * 0.9 - self.wave * 1.5)

        self.move_timer += 1
        if self.move_timer >= self.move_interval:
            self.move_timer = 0
            self.did_step = True
            leftmost = min(inv.x for inv in alive)
            rightmost = max(inv.x for inv in alive)
            if (self.direction == 1 and rightmost > WIDTH - 45) or (self.direction == -1 and leftmost < 45):
                self.direction *= -1
                for inv in alive:
                    inv.y += self.drop_amount
            else:
                step = 11 + self.wave * 0.5
                for inv in alive:
                    inv.x += self.direction * step

        # Enemy shooting
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
        else:
            chance = 0.015 + (1.0 - remaining / max(1, self.total_start)) * 0.04 + self.wave * 0.005
            if remaining > 0 and random.random() < chance:
                # Bottom-most per column
                columns = {}
                for inv in alive:
                    if inv.col not in columns or inv.y > columns[inv.col].y:
                        columns[inv.col] = inv
                if columns:
                    shooter = random.choice(list(columns.values()))
                    self.bullets.append(Bullet(
                        shooter.x, shooter.y + shooter.height // 2 + 4,
                        speed=4.5 + self.wave * 0.3, color=PINK, radius=4, is_player=False
                    ))
                    self.shoot_cooldown = max(15, 55 - remaining // 2 - self.wave * 3)

        for b in self.bullets:
            b.update()
        self.bullets = [b for b in self.bullets if b.active]

        # Reached bottom?
        for inv in alive:
            if inv.y + inv.height // 2 > HEIGHT - 130:
                return "reached_bottom"
        return "ok"

    def draw(self, surface, offset=(0, 0)):
        for inv in self.invaders:
            inv.draw(surface, offset, self.anim_frame)
        for b in self.bullets:
            b.draw(surface, offset)

    def check_player_bullets(self, player_bullets, particles):
        """Kill invaders hit by player bullets. Return total points scored."""
        score = 0
        for b in player_bullets:
            if not b.active or not b.is_player:
                continue
            for inv in self.invaders:
                if inv.alive and b.get_rect().colliderect(inv.get_rect()):
                    inv.alive = False
                    b.active = False
                    score += inv.points
                    spawn_explosion(particles, inv.x, inv.y, inv.color)
                    break
        return score


# =============================================================================
# DESTRUCTIBLE DEFENSE BUNKERS
# =============================================================================
class Barrier:
    def __init__(self, x, y):
        self.blocks = []
        # Classic bunker shape made of small blocks
        block_size = 6
        # Rough classic shape: wide base, cutouts
        layout = [
            "  ######  ",
            " ######## ",
            "##########",
            "###    ###",
            "###    ###",
            "###    ###",
        ]
        for row_idx, row in enumerate(layout):
            for col_idx, ch in enumerate(row):
                if ch == '#':
                    bx = x + col_idx * block_size
                    by = y + row_idx * block_size
                    self.blocks.append(pygame.Rect(bx, by, block_size, block_size))

    def check_bullet(self, bullet):
        """Return True if bullet hit a block (and destroy that block)."""
        if not bullet.active:
            return False
        for block in self.blocks[:]:
            if bullet.get_rect().colliderect(block):
                self.blocks.remove(block)
                bullet.active = False
                return True
        return False

    def check_invader(self, invader):
        if not invader.alive:
            return
        for block in self.blocks[:]:
            if invader.get_rect().colliderect(block):
                self.blocks.remove(block)

    def draw(self, surface, offset=(0, 0)):
        for block in self.blocks:
            r = pygame.Rect(block.x + offset[0], block.y + offset[1], block.w, block.h)
            pygame.draw.rect(surface, GREEN, r)
            pygame.draw.rect(surface, BLACK, r, 1)


# =============================================================================
# MYSTERY SAUCER
# =============================================================================
class UFO:
    def __init__(self):
        self.active = False
        self.x = 0
        self.y = 35
        self.speed = 0
        self.width = 50
        self.height = 22
        self.points = 100
        self.timer = 0

    def spawn(self):
        if self.active:
            return
        self.active = True
        if random.random() < 0.5:
            self.x = -60
            self.speed = 2.8
        else:
            self.x = WIDTH + 60
            self.speed = -2.8
        self.points = random.choice([100, 150, 200, 300])

    def update(self):
        if not self.active:
            self.timer += 1
            if self.timer > 400 and random.random() < 0.008:
                self.spawn()
                self.timer = 0
            return
        self.x += self.speed
        if self.x < -80 or self.x > WIDTH + 80:
            self.active = False

    def draw(self, surface, offset=(0, 0)):
        if not self.active:
            return
        cx = int(self.x + offset[0])
        cy = int(self.y + offset[1])
        pattern = (
            "000011110000",
            "001111111100",
            "011111111110",
            "110110110110",
            "111111111111",
            "001100001100",
        )
        draw_pixel_pattern(surface, pattern, cx - 24, cy - 12, 4, RED)

    def get_rect(self):
        return pygame.Rect(self.x - 25, self.y - 16, 50, 28)

    def check_hit(self, bullet, particles):
        if self.active and bullet.active and bullet.is_player and bullet.get_rect().colliderect(self.get_rect()):
            self.active = False
            bullet.active = False
            spawn_explosion(particles, self.x, self.y, ORANGE, count=20)
            return self.points
        return 0


# =============================================================================
# GAME
# =============================================================================
class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        if not pygame.font.get_init():
            pygame.font.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.canvas = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.scanlines = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for y in range(3, HEIGHT, 5):
            pygame.draw.line(self.scanlines, (0, 0, 0, 38), (0, y), (WIDTH, y))
        pygame.display.set_icon(self.make_window_icon())
        self.clock = pygame.time.Clock()
        self.font_large = PixelFont(48, bold=True)
        self.font_med = PixelFont(30, bold=True)
        self.font_small = PixelFont(21, bold=True)
        self.font_tiny = PixelFont(16)

        self.state = "menu"  # menu, help, about, playing, paused, gameover
        self.score = 0
        self.high_score = 0
        self.new_high_score = False
        self.wave = 1
        self.particles = []
        self.shake_timer = 0
        self.shake_intensity = 0
        self.shake_offset = (0, 0)
        self.menu_options = ("PLAY", "HELP", "ABOUT", "EXIT GAME")
        self.menu_index = 0
        self.menu_buttons = [
            pygame.Rect(WIDTH // 2 - 145, 255 + index * 62, 290, 48)
            for index in range(len(self.menu_options))
        ]
        self.back_button = pygame.Rect(WIDTH // 2 - 120, 500, 240, 48)
        self.restart_button = pygame.Rect(WIDTH // 2 - 145, 410, 290, 48)
        self.gameover_menu_button = pygame.Rect(WIDTH // 2 - 145, 476, 290, 48)
        self.audio = AudioManager()

        self.reset_game(new_run=True)

    @staticmethod
    def make_window_icon():
        icon = pygame.Surface((32, 32), pygame.SRCALPHA)
        icon.fill(BLACK)
        draw_pixel_pattern(icon, Invader.SPRITES[1][0], 5, 8, 2, GREEN)
        return icon

    def reset_game(self, new_run=False):
        if new_run:
            self.score = 0
            self.wave = 1
            self.new_high_score = False
        self.player = Player(WIDTH // 2, HEIGHT - 55)
        self.swarm = Swarm(start_y=70, wave=self.wave)
        self.barriers = [
            Barrier(90, 420),
            Barrier(270, 420),
            Barrier(450, 420),
            Barrier(630, 420),
        ]
        self.ufo = UFO()
        self.particles = []
        self.shake_timer = 0
        self.shake_offset = (0, 0)

    def start_new_game(self):
        self.reset_game(new_run=True)
        self.state = "playing"
        self.audio.play("select")

    def return_to_menu(self):
        self.state = "menu"
        self.menu_index = 0
        self.audio.play("select")

    def activate_menu_option(self):
        option = self.menu_options[self.menu_index]
        if option == "PLAY":
            self.start_new_game()
        elif option == "HELP":
            self.state = "help"
            self.audio.play("select")
        elif option == "ABOUT":
            self.state = "about"
            self.audio.play("select")
        elif option == "EXIT GAME":
            self.audio.play("select")
            return False
        return True

    def add_score(self, points):
        self.score += points
        if self.score > self.high_score:
            self.high_score = self.score
            self.new_high_score = True

    def trigger_shake(self, intensity=6, duration=12):
        self.shake_intensity = intensity
        self.shake_timer = duration

    def update_shake(self):
        if self.shake_timer > 0:
            self.shake_timer -= 1
            self.shake_offset = (
                random.randint(-self.shake_intensity, self.shake_intensity),
                random.randint(-self.shake_intensity, self.shake_intensity)
            )
            if self.shake_timer <= 0:
                self.shake_offset = (0, 0)
        else:
            self.shake_offset = (0, 0)

    def handle_collisions(self):
        # Player bullets vs invaders
        points = self.swarm.check_player_bullets(self.player.bullets, self.particles)
        if points > 0:
            self.add_score(points)
            self.audio.play("hit")

        # Player bullets vs barriers
        for b in self.player.bullets:
            for barrier in self.barriers:
                if barrier.check_bullet(b):
                    break

        # Player bullets vs UFO
        for b in self.player.bullets:
            pts = self.ufo.check_hit(b, self.particles)
            if pts > 0:
                self.add_score(pts)
                self.audio.play("ufo")
                self.trigger_shake(4, 8)

        # Enemy bullets vs player
        for b in self.swarm.bullets:
            if b.active and b.get_rect().colliderect(self.player.get_rect()):
                if self.player.hit():
                    b.active = False
                    self.audio.play("hurt")
                    spawn_explosion(self.particles, self.player.x, self.player.y, GREEN, 18)
                    self.trigger_shake(10, 18)
                    if not self.player.alive:
                        self.state = "gameover"

        # Enemy bullets vs barriers
        for b in self.swarm.bullets:
            for barrier in self.barriers:
                if barrier.check_bullet(b):
                    break

        # Invaders vs barriers (erode)
        for inv in self.swarm.get_alive():
            for barrier in self.barriers:
                barrier.check_invader(inv)

        # Invaders vs player
        for inv in self.swarm.get_alive():
            if inv.get_rect().colliderect(self.player.get_rect()):
                if self.player.hit():
                    self.audio.play("hurt")
                    spawn_explosion(self.particles, self.player.x, self.player.y, GREEN, 20)
                    self.trigger_shake(12, 20)
                    if not self.player.alive:
                        self.state = "gameover"

    def update_playing(self, keys):
        if self.player.update(keys):
            self.audio.play("shoot")
        status = self.swarm.update()
        if self.swarm.did_step:
            self.audio.play("march")
        self.ufo.update()
        self.update_shake()

        # Particles
        for p in self.particles[:]:
            p.update()
            if not p.is_alive():
                self.particles.remove(p)

        self.handle_collisions()

        if status == "cleared":
            self.wave += 1
            self.add_score(200 * self.wave)  # wave clear bonus
            self.swarm = Swarm(start_y=70 + min(30, self.wave * 4), wave=self.wave)
            # Keep barriers partially damaged for challenge, or recreate:
            # self.barriers = [Barrier(90, 420), ...]  # optional full reset
            self.trigger_shake(5, 10)
            self.audio.play("wave")
        elif status == "reached_bottom":
            self.player.alive = False
            self.state = "gameover"
            self.trigger_shake(15, 25)
            self.audio.play("hurt")

    def draw_hud(self, surface, offset=(0, 0)):
        # Score
        score_text = self.font_small.render(f"SCORE  {self.score:05d}", True, WHITE)
        surface.blit(score_text, (20 + offset[0], 12 + offset[1]))

        # High score
        hs_text = self.font_small.render(f"HI  {self.high_score:05d}", True, WHITE)
        surface.blit(hs_text, (WIDTH // 2 - 50 + offset[0], 12 + offset[1]))

        # Wave
        wave_text = self.font_small.render(f"WAVE {self.wave}", True, CYAN)
        surface.blit(wave_text, (WIDTH - 110 + offset[0], 12 + offset[1]))

        # Remaining cannons
        lives_label = self.font_tiny.render("LIVES", True, WHITE)
        surface.blit(lives_label, (18 + offset[0], HEIGHT - 29 + offset[1]))
        for i in range(self.player.lives):
            lx = 92 + i * 30 + offset[0]
            ly = HEIGHT - 24 + offset[1]
            pygame.draw.rect(surface, GREEN, (lx - 11, ly, 22, 5))
            pygame.draw.rect(surface, GREEN, (lx - 7, ly - 5, 14, 5))
            pygame.draw.rect(surface, GREEN, (lx - 2, ly - 9, 4, 4))

        if not self.audio.enabled:
            hud_sound = "N/A"
        else:
            hud_sound = "OFF" if self.audio.muted else "ON"
        controls = self.font_tiny.render(
            f"P PAUSE   M SOUND {hud_sound}", True, GRAY
        )
        surface.blit(
            controls,
            (WIDTH - controls.get_width() - 18 + offset[0], HEIGHT - 27 + offset[1]),
        )

    def draw_button(self, surface, rect, label, color=RED, selected=False):
        active = selected or rect.collidepoint(pygame.mouse.get_pos())
        fill = RED if active else BLACK
        border = WHITE if active else color
        pygame.draw.rect(surface, fill, rect)
        pygame.draw.rect(surface, border, rect, width=3)
        text = self.font_med.render(label, True, WHITE if active else color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2),
        )

    @staticmethod
    def draw_invader_emblem(surface, center):
        cx, cy = center
        draw_pixel_pattern(
            surface,
            Invader.SPRITES[1][0],
            cx - 33,
            cy - 24,
            6,
            GREEN,
        )

    def draw_menu(self, surface):
        surface.fill(DEEP_SPACE)

        title = self.font_large.render("AC'S SPACE INVADERS", True, WHITE)
        surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 48))

        sub = self.font_med.render("PY PORT 0.1", True, RED)
        surface.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 108))

        edition = self.font_tiny.render("FAMICOM 8-BIT EDITION", True, GREEN)
        surface.blit(edition, (WIDTH // 2 - edition.get_width() // 2, 148))

        self.draw_invader_emblem(surface, (WIDTH // 2, 205))

        for index, (label, rect) in enumerate(zip(self.menu_options, self.menu_buttons)):
            self.draw_button(
                surface,
                rect,
                label,
                selected=index == self.menu_index,
            )

        if not self.audio.enabled:
            sound_state = "NO DEVICE"
        else:
            sound_state = "OFF" if self.audio.muted else "ON"
        sound = self.font_tiny.render(
            f"2A03 SFX: {sound_state}",
            True,
            GRAY if sound_state != "ON" else GREEN,
        )
        surface.blit(sound, (WIDTH - sound.get_width() - 18, 18))
        nav = self.font_tiny.render("UP/DOWN + ENTER OR MOUSE", True, GRAY)
        surface.blit(nav, (WIDTH // 2 - nav.get_width() // 2, 520))
        if self.high_score > 0:
            hs = self.font_tiny.render(
                f"SESSION HIGH SCORE: {self.high_score}", True, YELLOW
            )
            surface.blit(hs, (WIDTH // 2 - hs.get_width() // 2, 552))

    def draw_help(self, surface):
        surface.fill(DEEP_SPACE)
        title = self.font_large.render("HELP", True, WHITE)
        surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 54))

        panel = pygame.Rect(105, 130, 590, 310)
        pygame.draw.rect(surface, BLACK, panel)
        pygame.draw.rect(surface, RED, panel, width=4)
        lines = (
            ("LEFT / RIGHT OR A / D", "MOVE CANNON"),
            ("SPACE OR UP", "FIRE LASER"),
            ("P", "PAUSE GAME"),
            ("M", "TOGGLE SOUND"),
            ("ESC", "PAUSE / MAIN MENU"),
        )
        for index, (key, action) in enumerate(lines):
            y = 160 + index * 48
            key_text = self.font_small.render(key, True, GREEN)
            action_text = self.font_small.render(action, True, WHITE)
            surface.blit(key_text, (135, y))
            surface.blit(action_text, (470, y))

        tip = self.font_tiny.render(
            "DESTROY THE FLEET BEFORE IT REACHES EARTH.", True, YELLOW
        )
        surface.blit(tip, (WIDTH // 2 - tip.get_width() // 2, 420))
        self.draw_button(surface, self.back_button, "BACK")

    def draw_about(self, surface):
        surface.fill(DEEP_SPACE)
        title = self.font_large.render("ABOUT", True, WHITE)
        surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 54))

        self.draw_invader_emblem(surface, (WIDTH // 2, 150))
        lines = (
            "AC'S SPACE INVADERS PY PORT 0.1",
            "A SINGLE-FILE PYTHON 3.14 GAME",
            "FAMICOM-STYLE PIXEL GRAPHICS",
            "PROCEDURAL 2A03-INSPIRED SFX",
            "NO EXTERNAL ASSETS REQUIRED",
        )
        for index, line in enumerate(lines):
            color = RED if index == 0 else WHITE
            text = self.font_small.render(line, True, color)
            surface.blit(
                text,
                (WIDTH // 2 - text.get_width() // 2, 225 + index * 39),
            )
        self.draw_button(surface, self.back_button, "BACK")

    def draw_gameover(self, surface):
        surface.fill(DEEP_SPACE)

        go = self.font_large.render("GAME OVER", True, RED)
        surface.blit(go, (WIDTH // 2 - go.get_width() // 2, 180))

        message = self.font_med.render("EARTH DEFENSE FAILED", True, GREEN)
        surface.blit(message, (WIDTH // 2 - message.get_width() // 2, 260))

        sc = self.font_med.render(f"Final Score: {self.score}", True, WHITE)
        surface.blit(sc, (WIDTH // 2 - sc.get_width() // 2, 320))

        if self.new_high_score and self.score > 0:
            newhs = self.font_small.render("NEW HIGH SCORE!", True, YELLOW)
            surface.blit(newhs, (WIDTH // 2 - newhs.get_width() // 2, 370))

        self.draw_button(surface, self.restart_button, "TRY AGAIN")
        self.draw_button(surface, self.gameover_menu_button, "MAIN MENU")

        esc = self.font_tiny.render("R / SPACE RESTART   ESC MAIN MENU", True, GRAY)
        surface.blit(esc, (WIDTH // 2 - esc.get_width() // 2, 545))

    def draw_playing(self, surface):
        surface.fill(DEEP_SPACE)
        offset = self.shake_offset

        # Barriers
        for barrier in self.barriers:
            barrier.draw(surface, offset)

        # UFO
        self.ufo.draw(surface, offset)

        # Swarm
        self.swarm.draw(surface, offset)

        # Player
        self.player.draw(surface, offset)

        # Particles
        for p in self.particles:
            p.draw(surface, offset)

        # HUD
        self.draw_hud(surface, offset)
        pygame.draw.line(
            surface,
            GREEN,
            (12 + offset[0], HEIGHT - 42 + offset[1]),
            (WIDTH - 12 + offset[0], HEIGHT - 42 + offset[1]),
            3,
        )

    def draw_paused(self, surface):
        self.draw_playing(surface)
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 185))
        surface.blit(shade, (0, 0))
        panel = pygame.Rect(WIDTH // 2 - 180, HEIGHT // 2 - 85, 360, 170)
        pygame.draw.rect(surface, BLACK, panel)
        pygame.draw.rect(surface, RED, panel, width=4)
        paused = self.font_large.render("PAUSED", True, WHITE)
        surface.blit(paused, (WIDTH // 2 - paused.get_width() // 2, 245))
        hint = self.font_small.render("PRESS P TO CONTINUE", True, GREEN)
        surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 325))

    def present(self):
        """Present once at 1:1 so pixel-font glyphs are never resampled."""
        self.screen.blit(self.canvas, (0, 0))
        self.screen.blit(self.scanlines, (0, 0))

    def run(self):
        running = True
        while running:
            keys = pygame.key.get_pressed()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_m:
                        self.audio.toggle_mute()

                    if self.state == "menu":
                        if event.key in (pygame.K_UP, pygame.K_w):
                            self.menu_index = (self.menu_index - 1) % len(self.menu_options)
                            self.audio.play("select")
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            self.menu_index = (self.menu_index + 1) % len(self.menu_options)
                            self.audio.play("select")
                        elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            running = self.activate_menu_option()
                        elif event.key == pygame.K_ESCAPE:
                            running = False

                    elif self.state in ("help", "about"):
                        if event.key in (
                            pygame.K_ESCAPE,
                            pygame.K_BACKSPACE,
                            pygame.K_SPACE,
                            pygame.K_RETURN,
                        ):
                            self.return_to_menu()

                    elif self.state == "playing":
                        if event.key in (pygame.K_p, pygame.K_ESCAPE):
                            self.state = "paused"
                            self.audio.play("select")

                    elif self.state == "paused":
                        if event.key == pygame.K_p:
                            self.state = "playing"
                            self.audio.play("select")
                        elif event.key == pygame.K_ESCAPE:
                            self.return_to_menu()

                    elif self.state == "gameover":
                        if event.key in (pygame.K_r, pygame.K_SPACE, pygame.K_RETURN):
                            self.start_new_game()
                        elif event.key == pygame.K_ESCAPE:
                            self.return_to_menu()

                if event.type == pygame.MOUSEMOTION and self.state == "menu":
                    for index, rect in enumerate(self.menu_buttons):
                        if rect.collidepoint(event.pos):
                            self.menu_index = index
                            break

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.state == "menu":
                        for index, rect in enumerate(self.menu_buttons):
                            if rect.collidepoint(event.pos):
                                self.menu_index = index
                                running = self.activate_menu_option()
                                break
                    elif self.state in ("help", "about"):
                        if self.back_button.collidepoint(event.pos):
                            self.return_to_menu()
                    elif self.state == "gameover":
                        if self.restart_button.collidepoint(event.pos):
                            self.start_new_game()
                        elif self.gameover_menu_button.collidepoint(event.pos):
                            self.return_to_menu()

            if self.state == "playing":
                self.update_playing(keys)

            # Draw
            if self.state == "menu":
                self.draw_menu(self.canvas)
            elif self.state == "help":
                self.draw_help(self.canvas)
            elif self.state == "about":
                self.draw_about(self.canvas)
            elif self.state == "playing":
                self.draw_playing(self.canvas)
            elif self.state == "paused":
                self.draw_paused(self.canvas)
            elif self.state == "gameover":
                self.draw_gameover(self.canvas)

            self.present()
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    game = Game()
    game.run()
