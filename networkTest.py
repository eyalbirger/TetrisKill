import pygame

pygame.init()

WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Online Pygame Game")

clock = pygame.time.Clock()

player_x = 400
player_y = 300
player_speed = 5
player_size = 40

running = True

while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()

    if keys[pygame.K_LEFT]:
        player_x -= player_speed
    if keys[pygame.K_RIGHT]:
        player_x += player_speed
    if keys[pygame.K_UP]:
        player_y -= player_speed
    if keys[pygame.K_DOWN]:
        player_y += player_speed

    screen.fill((30, 30, 30))

    pygame.draw.rect(
        screen,
        (0, 200, 255),
        (player_x, player_y, player_size, player_size)
    )

    pygame.display.flip()

pygame.quit()