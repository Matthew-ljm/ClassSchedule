import pygame
from pygame import Window

pygame.init()
screen = pygame.display.set_mode((400, 300), pygame.NOFRAME)
win = Window.from_display_module()
win.opacity = 0.1   # 半透明

running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
    screen.fill((255, 0, 0))
    pygame.display.flip()
pygame.quit()