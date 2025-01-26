import pygame
import random
import csv
from queue import PriorityQueue
from datetime import datetime
import threading
import time
import math

# Initialize Pygame
pygame.init()
pygame.font.init()

# Constants
GRID_SIZE = 25
WINDOW_SIZE = 800
CELL_SIZE = WINDOW_SIZE // GRID_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + 100

# Modern Color Palette
BLACK = (34, 40, 49)
WHITE = (250, 250, 250)
RED = (235, 87, 87)
GREEN = (72, 190, 145)
BLUE = (98, 155, 245)
YELLOW = (255, 214, 102)
GRAY = (189, 195, 199)
BUILDING_COLOR = (149, 165, 166)
PATH_COLOR = (236, 240, 241)
ALERT_COLOR = (242, 153, 74)
BG_COLOR = (248, 250, 252)

# Entity types
EMPTY = 0
HOSPITAL = 1
BUILDING = 2
DRONE = 3
OBSTACLE = 4

class EnhancedGridSim:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_SIZE + 300, TOTAL_HEIGHT))
        pygame.display.set_caption("Grid Simulation")
        
        try:
            self.font = pygame.font.SysFont('Inter', 24)
            self.small_font = pygame.font.SysFont('Inter', 16)
        except:
            self.font = pygame.font.SysFont('Arial', 24)
            self.small_font = pygame.font.SysFont('Arial', 16)
        
        # Initialize components
        self.grid = [[EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.hospitals = {}
        self.buildings = set()
        self.drones = []
        self.moving_obstacles = []
        self.particle_systems = []
        
        # Hospital supplies and needs
        self.possible_supplies = {
            'Medical': {'production': 10, 'consumption': 5},
            'Blood': {'production': 8, 'consumption': 4},
            'Equipment': {'production': 5, 'consumption': 3},
            'Supplies': {'production': 7, 'consumption': 4}
        }
        
        self.possible_needs = list(self.possible_supplies.keys())
        
        # Stats tracking
        self.total_deliveries = 0
        self.active_routes = 0
        self.emergency_count = 0
        
        # State management
        self.edit_mode = True
        self.simulation_running = False
        self.selected_type = None
        self.active_hospital_drones = set()
        
        # Timing controls
        self.drone_move_timer = 0
        self.drone_move_interval = 2
        self.obstacle_spawn_timer = 0
        self.obstacle_spawn_interval = 4
        self.obstacle_move_timer = 0
        self.obstacle_move_interval = 6
        self.max_obstacles = 200
        
        # Setup
        self.setup_ui()
        self.alert_file = "simulation_alerts.csv"
        self.create_alert_file()
        self.alert_thread = None
        self.running = True
        self.deploy_count = 1
        self.deploy_active = False
        self.deploy_timer = 0
        self.deploy_interval = 60  # 1 second at 60 FPS
        self.dashboard_scroll_y = 0  # Tracks the scroll position
        self.dashboard_height = TOTAL_HEIGHT

    def setup_ui(self):
        button_height = 50
        button_width = (WINDOW_SIZE - 40) // 5
        spacing = 8
        button_y = WINDOW_SIZE + 25
        
        self.buttons = {
            'hospital': pygame.Rect(spacing, button_y, button_width, button_height),
            'building': pygame.Rect(button_width + 2*spacing, button_y, button_width, button_height),
            'start': pygame.Rect(2*button_width + 3*spacing, button_y, button_width, button_height),
            'stop': pygame.Rect(3*button_width + 4*spacing, button_y, button_width, button_height),
            'clear': pygame.Rect(4*button_width + 5*spacing, button_y, button_width, button_height)
        }
        
        colors = {
            'hospital': GREEN,
            'building': BUILDING_COLOR,
            'start': GREEN,
            'stop': RED,
            'clear': GRAY
        }
        
        self.button_surfaces = {}
        self.button_labels = {}
        
        for name, rect in self.buttons.items():
            surface = pygame.Surface((button_width, button_height))
            surface.fill(colors.get(name, GRAY))
            self.button_surfaces[name] = surface
            
            text = name.capitalize()
            label = self.font.render(text, True, WHITE)
            self.button_labels[name] = label

    def create_alert_file(self):
        with open(self.alert_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['ID', 'Timestamp', 'Type', 'Origin', 'Destination', 'Status'])

    def process_alerts(self):
        if not hasattr(self, 'alert_file') or not self.alert_file:
            return
            
        try:
            with open(self.alert_file, 'r') as file:
                reader = csv.DictReader(file)
                alerts = list(reader)
            
            for alert in alerts:
                if (not any(d['id'] == alert['ID'] for d in self.drones) and 
                    alert['Status'] == 'Active'):
                    origin_hospital = None
                    dest_hospital = None
                    
                    for pos, hospital in self.hospitals.items():
                        if hospital['id'] == alert['Origin']:
                            origin_hospital = pos
                        if hospital['id'] == alert['Destination']:
                            dest_hospital = pos
                    
                    if origin_hospital and dest_hospital:
                        self.drones.append({
                            'id': alert['ID'],
                            'pos': origin_hospital,
                            'origin_hospital': alert['Origin'],
                            'destination': dest_hospital,
                            'path': self.find_path(origin_hospital, dest_hospital),
                            'type': alert['Type'],
                            'trail': []
                        })
        except (FileNotFoundError, KeyError, csv.Error) as e:
            print(f"Error processing alerts: {e}")

    def generate_alerts(self):
        alert_id = 1
        while self.simulation_running:
            if len(self.hospitals) >= 2:
                available_hospitals = []
                destination_hospitals = []
                
                for pos, hospital in self.hospitals.items():
                    if hospital['drones'] < 3:
                        available_hospitals.append((pos, hospital))
                    if hospital['needs']:
                        destination_hospitals.append((pos, hospital))
                
                if available_hospitals and destination_hospitals:
                    origin_pos, origin_hospital = random.choice(available_hospitals)
                    dest_pos, dest_hospital = random.choice(destination_hospitals)
                    
                    if origin_pos != dest_pos:
                        supply_type = random.choice(list(dest_hospital['needs'].keys()))
                        self.create_new_drone(origin_hospital, origin_pos, dest_hospital, dest_pos, supply_type)
                        alert_id += 1
                
                time.sleep(random.randint(2, 4))

    def create_new_drone(self, origin_hospital, origin_pos, dest_hospital, dest_pos, supply_type):
        drone_id = f"D{len(self.drones) + 1}"
        self.drones.append({
            'id': drone_id,
            'pos': origin_pos,
            'origin_hospital': origin_hospital['id'],
            'destination': dest_pos,
            'path': self.find_path(origin_pos, dest_pos),
            'type': supply_type,
            'trail': []
        })
        origin_hospital['drones'] += 1
        self.active_routes += 1

    def create_glow_effect(self, radius, color):
        size = radius * 2
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        
        for i in range(radius, 0, -1):
            alpha = int((1 - (i / radius)) * 128)
            pygame.draw.circle(surface, (*color, alpha), (radius, radius), i)
        
        return surface

    def add_particle_system(self, pos, color):
        particles = [self.create_particle(pos) for _ in range(20)]
        self.particle_systems.append({
            'pos': pos,
            'particles': particles,
            'color': color,
            'lifetime': 30
        })

    def create_particle(self, pos):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.5, 2.0)
        dx = speed * math.cos(angle)
        dy = speed * math.sin(angle)
        return {
            'pos': [pos[0] * CELL_SIZE + CELL_SIZE/2, pos[1] * CELL_SIZE + CELL_SIZE/2],
            'vel': [dx, dy],
            'life': random.randint(20, 40)
        }

    def update_particles(self):
        for system in self.particle_systems[:]:
            for particle in system['particles'][:]:
                particle['pos'][0] += particle['vel'][0]
                particle['pos'][1] += particle['vel'][1]
                particle['life'] -= 1
                
                if particle['life'] <= 0:
                    system['particles'].remove(particle)
            
            system['lifetime'] -= 1
            if system['lifetime'] <= 0 or not system['particles']:
                self.particle_systems.remove(system)

    def update_drones(self):
        self.drone_move_timer += 1
        if self.drone_move_timer < self.drone_move_interval:
            return
        
        self.drone_move_timer = 0
        
        for drone in self.drones[:]:
            if not drone['path']:
                continue
                
            next_pos = drone['path'][0]
            current_pos = drone['pos']
            
            if self.check_obstacle_proximity(next_pos):
                new_path = self.find_safe_path(current_pos, drone['destination'])
                if new_path:
                    drone['path'] = new_path
                continue
            
            if self.is_valid_move(*next_pos):
                x, y = current_pos
                next_x, next_y = next_pos
                dx = max(-1, min(1, next_x - x))
                dy = max(-1, min(1, next_y - y))
                new_pos = (x + dx, y + dy)
                
                drone['trail'].append(drone['pos'])
                if len(drone['trail']) > 10:
                    drone['trail'].pop(0)
                
                drone['pos'] = new_pos
                
                if new_pos == next_pos:
                    drone['path'].pop(0)
                
                if new_pos == drone['destination']:
                    self.complete_delivery(drone)
            else:
                new_path = self.find_safe_path(current_pos, drone['destination'])
                if new_path:
                    drone['path'] = new_path

    def update_moving_obstacles(self):
        self.obstacle_move_timer += 1
        if self.obstacle_move_timer < self.obstacle_move_interval:
            return
        
        self.obstacle_move_timer = 0
        
        self.obstacle_spawn_timer += 1
        if (self.obstacle_spawn_timer >= self.obstacle_spawn_interval and 
            len(self.moving_obstacles) < self.max_obstacles):
            for _ in range(3):
                self.spawn_moving_obstacle()
            self.obstacle_spawn_timer = 0
        
        for obstacle in self.moving_obstacles[:]:
            x, y = map(int, obstacle['pos'])
            dx, dy = obstacle['direction']
            
            obstacle['trail'].append((x, y))
            if len(obstacle['trail']) > 5:
                obstacle['trail'].pop(0)
            
            if random.random() < 0.15:
                if random.random() < 0.5:
                    dx = random.choice([-1, 1])
                    dy = 0
                else:
                    dx = 0
                    dy = random.choice([-1, 1])
                obstacle['direction'] = (dx, dy)
            
            new_x = x + dx
            new_y = y + dy
            
            if not (0 <= new_x < GRID_SIZE and 0 <= new_y < GRID_SIZE):
                self.moving_obstacles.remove(obstacle)
                continue
            
            obstacle['pos'] = (new_x, new_y)
            obstacle['transparent'] = self.grid[new_y][new_x] == HOSPITAL
            
            if obstacle['transparent']:
                self.add_particle_system((new_x, new_y), BLUE)

    def spawn_moving_obstacle(self):
        if random.random() < 0.5:
            x = random.choice([0, GRID_SIZE-1])
            y = random.randint(0, GRID_SIZE-1)
            dx = 1 if x == 0 else -1
            dy = 0
        else:
            x = random.randint(0, GRID_SIZE-1)
            y = random.choice([0, GRID_SIZE-1])
            dx = 0
            dy = 1 if y == 0 else -1
        
        self.moving_obstacles.append({
            'pos': (x, y),
            'direction': (dx, dy),
            'transparent': False,
            'trail': []
        })

    def find_path(self, start, end):
        frontier = PriorityQueue()
        frontier.put((0, start))
        came_from = {start: None}
        cost_so_far = {start: 0}

        while not frontier.empty():
            current = frontier.get()[1]
            if current == end:
                break

            for next_pos in self.get_neighbors(current):
                obstacle_cost = self.check_obstacle_proximity(next_pos) * 2
                new_cost = cost_so_far[current] + 1 + obstacle_cost
                
                if next_pos not in cost_so_far or new_cost < cost_so_far[next_pos]:
                    cost_so_far[next_pos] = new_cost
                    priority = new_cost + self.heuristic(end, next_pos)
                    frontier.put((priority, next_pos))
                    came_from[next_pos] = current

        if end not in came_from:
            return []
            
        path = []
        current = end
        while current != start:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def get_neighbors(self, pos):
        neighbors = []
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0),
                       (1, 1), (-1, 1), (1, -1), (-1, -1)]:
            new_x, new_y = pos[0] + dx, pos[1] + dy
            if self.is_valid_move(new_x, new_y):
                neighbors.append((new_x, new_y))
        return neighbors

    def heuristic(self, a, b):
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    def check_obstacle_proximity(self, pos, radius=2):
        x, y = pos
        count = 0
        for obstacle in self.moving_obstacles:
            obs_x, obs_y = map(int, obstacle['pos'])
            if abs(obs_x - x) <= radius and abs(obs_y - y) <= radius:
                count += 1
        return count

    def is_valid_move(self, x, y):
        if not (0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE):
            return False
        return self.grid[y][x] != BUILDING

    def handle_click(self, pos):
        x, y = pos[0] // CELL_SIZE, pos[1] // CELL_SIZE
        
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE and self.edit_mode and self.selected_type:
            if self.grid[y][x] == EMPTY:
                if self.selected_type == 'building':
                    self.grid[y][x] = BUILDING
                    self.buildings.add((x, y))
                    print(f"Building added at ({x}, {y})")  # Debug print
                elif self.selected_type == 'hospital':
                    hospital_id = f"H{len(self.hospitals) + 1}"
                    specialties = random.sample(list(self.possible_supplies.keys()), 2)
                    needs = random.sample([s for s in self.possible_supplies.keys() if s not in specialties], 2)
                    
                    self.hospitals[(x, y)] = {
                        'id': hospital_id,
                        'specialties': {s: self.possible_supplies[s]['production'] for s in specialties},
                        'needs': {n: 0 for n in needs},
                        'drones': 0,
                        'pos': (x, y)
                    }
                    
                    self.grid[y][x] = HOSPITAL
                    self.add_particle_system((x, y), GREEN)
                    print(f"Hospital added at ({x}, {y})")  # Debug print

    def draw(self):
        self.screen.fill(BG_COLOR)
        
        # Draw grid and elements
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(self.screen, (236, 240, 243), rect, 1)

        self.draw_trails()
        self.draw_paths()
        self.draw_buildings()
        self.draw_obstacles()
        self.draw_drones()
        
        # Draw particles
        for system in self.particle_systems:
            for particle in system['particles']:
                alpha = min(255, particle['life'] * 8)
                color = (*system['color'], alpha)
                pos = (int(particle['pos'][0]), int(particle['pos'][1]))
                pygame.draw.circle(self.screen, color, pos, 2)
        
        self.draw_dashboard()
        self.draw_buttons()
        
        pygame.display.flip()

    def draw_trails(self):
        for obstacle in self.moving_obstacles:
            for i, (trail_x, trail_y) in enumerate(obstacle['trail']):
                alpha = int(255 * (i + 1) / len(obstacle['trail']))
                trail_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                pygame.draw.rect(trail_surface, (*BLUE, alpha // 4), trail_surface.get_rect())
                self.screen.blit(trail_surface, (trail_x * CELL_SIZE, trail_y * CELL_SIZE))
        
        for drone in self.drones:
            for i, (trail_x, trail_y) in enumerate(drone['trail']):
                alpha = int(255 * (i + 1) / len(drone['trail']))
                trail_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                pygame.draw.rect(trail_surface, (*RED, alpha // 4), trail_surface.get_rect())
                self.screen.blit(trail_surface, (trail_x * CELL_SIZE, trail_y * CELL_SIZE))

    def draw_paths(self):
        for drone in self.drones:
            if drone['path']:
                path_surface = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE), pygame.SRCALPHA)
                for path_pos in drone['path']:
                    x, y = path_pos
                    rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    pygame.draw.rect(path_surface, (*PATH_COLOR, 128), rect)
                self.screen.blit(path_surface, (0, 0))

    def draw_buildings(self):
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                if self.grid[y][x] == BUILDING:
                    rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    pygame.draw.rect(self.screen, BUILDING_COLOR, rect)
                    pygame.draw.rect(self.screen, WHITE, rect, 1)
                elif self.grid[y][x] == HOSPITAL:
                    rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    pygame.draw.rect(self.screen, GREEN, rect)
                    pygame.draw.rect(self.screen, WHITE, rect, 2)
                    
                    # Draw hospital ID
                    hospital = self.hospitals.get((x, y))
                    if hospital:
                        text = self.small_font.render(hospital['id'], True, WHITE)
                        text_rect = text.get_rect(center=rect.center)
                        self.screen.blit(text, text_rect)

    def draw_obstacles(self):
        for obstacle in self.moving_obstacles:
            x, y = map(int, obstacle['pos'])
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            
            if obstacle['transparent']:
                obstacle_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                pygame.draw.rect(obstacle_surface, (*BLUE, 128), obstacle_surface.get_rect())
                self.screen.blit(obstacle_surface, rect)
            else:
                pygame.draw.rect(self.screen, BLUE, rect)
                pygame.draw.rect(self.screen, (98, 155, 245), rect, 2)

    def draw_drones(self):
        for drone in self.drones:
            x, y = drone['pos']
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            
            glow = self.create_glow_effect(CELL_SIZE, RED)
            glow_pos = (x * CELL_SIZE - CELL_SIZE//2, y * CELL_SIZE - CELL_SIZE//2)
            self.screen.blit(glow, glow_pos)
            
            pygame.draw.rect(self.screen, RED, rect)
            pygame.draw.rect(self.screen, (235, 87, 87), rect, 2)
    def deploy_drone(self):
        hospitals = list(self.hospitals.items())
        if len(hospitals) >= 2:
            src_pos, src_hospital = random.choice(hospitals)
            possible_dests = [(pos, hosp) for pos, hosp in hospitals 
                            if pos != src_pos and hosp['needs']]
            
            if possible_dests and src_hospital['drones'] < 3:
                dest_pos, dest_hospital = random.choice(possible_dests)
                supply_type = random.choice(list(dest_hospital['needs'].keys()))
                self.create_new_drone(src_hospital, src_pos, dest_hospital, dest_pos, supply_type)
        
    def handle_mouse_event(self, event):
        mouse_pos = event.pos
        
        # Handle scroll events
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # Scroll up
                self.dashboard_scroll_y = max(0, self.dashboard_scroll_y - 20)
            elif event.button == 5:  # Scroll down
                self.dashboard_scroll_y = min(self.dashboard_height - TOTAL_HEIGHT, self.dashboard_scroll_y + 20)
        
        # Handle deploy controls when simulation is running
        if self.simulation_running:
            if hasattr(self, 'inc_button') and self.inc_button.collidepoint(mouse_pos):
                self.deploy_count = min(5, self.deploy_count + 1)
            elif hasattr(self, 'dec_button') and self.dec_button.collidepoint(mouse_pos):
                self.deploy_count = max(1, self.deploy_count - 1)
            elif hasattr(self, 'deploy_button') and self.deploy_button.collidepoint(mouse_pos):
                self.deploy_active = not self.deploy_active
            elif not self.deploy_active and hasattr(self, 'manual_deploy_button') and self.manual_deploy_button.collidepoint(mouse_pos):
                self.deploy_single_drone()
        
        # Handle main buttons
        for name, rect in self.buttons.items():
            if rect.collidepoint(mouse_pos):
                if name in ['hospital', 'building']:
                    self.selected_type = name
                elif name == 'start' and self.edit_mode:
                    self.handle_simulation_start()
                elif name == 'stop':
                    self.simulation_running = False
                    self.edit_mode = True
                    self.deploy_active = False  # Reset deploy state
                elif name == 'clear':
                    self.clear_simulation()
        
        # Handle grid clicks
        if mouse_pos[1] < WINDOW_SIZE:
            self.handle_click(mouse_pos)

    def draw_dashboard(self):
        dashboard_rect = pygame.Rect(WINDOW_SIZE, 0, 300, TOTAL_HEIGHT)
        pygame.draw.rect(self.screen, WHITE, dashboard_rect)
        pygame.draw.line(self.screen, GRAY, (WINDOW_SIZE, 0), (WINDOW_SIZE, TOTAL_HEIGHT), 2)
        
        x = WINDOW_SIZE + 20
        y = 20  # Fixed y-coordinate for stats

        # Stats (fixed position, not affected by scrolling)
        titles = [
            f"Deliveries: {self.total_deliveries}",
            f"Active Routes: {self.active_routes}",
            f"Emergencies: {self.emergency_count}"
        ]
        
        for title in titles:
            text = self.small_font.render(title, True, BLACK)
            self.screen.blit(text, (x, y))
            y += 25

        y += 20  # Add spacing after stats

        # Hospital details (scrollable)
        for pos, hospital in self.hospitals.items():
            text = self.small_font.render(f"{hospital['id']} (Drones: {hospital['drones']})", True, GREEN)
            self.screen.blit(text, (x, y - self.dashboard_scroll_y))  # Apply scroll offset
            y += 25
            
            for supply, amount in hospital['specialties'].items():
                text = self.small_font.render(f"+ {supply}: {amount}", True, BLUE)
                self.screen.blit(text, (x + 20, y - self.dashboard_scroll_y))  # Apply scroll offset
                y += 20
            
            for need in hospital['needs']:
                text = self.small_font.render(f"- {need}", True, RED)
                self.screen.blit(text, (x + 20, y - self.dashboard_scroll_y))  # Apply scroll offset
                y += 20
            y += 10
        
        # Update dashboard height based on content
        self.dashboard_height = y + self.dashboard_scroll_y

        # Auto deploy toggle (positioned at the bottom, fixed)
        y = TOTAL_HEIGHT - 120
        if self.simulation_running:
            deploy_rect = pygame.Rect(x, y, 260, 40)
            color = GREEN if self.deploy_active else GRAY
            pygame.draw.rect(self.screen, color, deploy_rect, border_radius=4)
            status = "Auto Deploy: ON" if self.deploy_active else "Auto Deploy: OFF"
            text = self.font.render(status, True, WHITE)
            text_rect = text.get_rect(center=deploy_rect.center)
            self.screen.blit(text, text_rect)
            self.deploy_button = deploy_rect
            
            # Manual deploy button (when auto is off)
            if not self.deploy_active:
                y += 50
                manual_rect = pygame.Rect(x, y, 260, 40)
                pygame.draw.rect(self.screen, BLUE, manual_rect, border_radius=4)
                text = self.font.render("Deploy Drones", True, WHITE)
                text_rect = text.get_rect(center=manual_rect.center)
                self.screen.blit(text, text_rect)
                self.manual_deploy_button = manual_rect

    def update_hospital_needs(self):
        for hospital in self.hospitals.values():
            # 5% chance to update needs
            if random.random() < 0.05:
                available_supplies = [s for s in self.possible_supplies.keys() 
                                if s not in hospital['needs']]
                if available_supplies:
                    new_need = random.choice(available_supplies)
                    hospital['needs'][new_need] = 0

    def draw_buttons(self):
        for name, rect in self.buttons.items():
            if self.selected_type == name:
                pygame.draw.rect(self.screen, (*YELLOW, 128), rect, border_radius=4)
            
            self.screen.blit(self.button_surfaces[name], rect)
            label = self.button_labels[name]
            label_rect = label.get_rect(center=rect.center)
            self.screen.blit(label, label_rect)
    
    def deploy_drones(self):
        if not self.deploy_active or not self.simulation_running:
            return
            
        self.deploy_timer += 1
        if self.deploy_timer < self.deploy_interval:
            return
            
        self.deploy_timer = 0
        
        # Deploy based on count
        for _ in range(self.deploy_count):
            self.deploy_single_drone()

    def deploy_single_drone(self):
        hospitals = list(self.hospitals.items())
        if len(hospitals) >= 2:
            src_pos, src_hospital = random.choice(hospitals)
            possible_dests = [(pos, hosp) for pos, hosp in hospitals 
                            if pos != src_pos and len(hosp['needs']) > 0]
            
            if possible_dests and src_hospital['drones'] < 3:
                dest_pos, dest_hospital = random.choice(possible_dests)
                supply_type = random.choice(list(dest_hospital['needs'].keys()))
                self.create_new_drone(src_hospital, src_pos, dest_hospital, dest_pos, supply_type)

    def update_simulation(self):
        if not self.simulation_running:
            return

        if self.deploy_active:
            self.deploy_drones()
        
        self.update_drones()
        self.update_moving_obstacles()
        self.update_particles()
        self.process_alerts()
        self.update_hospital_needs()


    def complete_delivery(self, drone):
        self.total_deliveries += 1
        self.active_routes -= 1
        
        # Update origin hospital
        for hospital in self.hospitals.values():
            if hospital['id'] == drone['origin_hospital']:
                hospital['drones'] -= 1
                break
        
        # Update destination hospital's needs
        dest_pos = drone['destination']
        if dest_pos in self.hospitals:
            dest_hospital = self.hospitals[dest_pos]
            supply_type = drone['type']
            if supply_type in dest_hospital['needs']:
                dest_hospital['needs'].pop(supply_type)
        
        self.add_particle_system(drone['destination'], GREEN)
        self.drones.remove(drone)

    def find_safe_path(self, start, end):
        return self.find_path(start, end)

    def handle_simulation_start(self):
        self.drones.clear()
        self.active_hospital_drones.clear()
        self.create_alert_file()
        
        self.edit_mode = False
        self.simulation_running = True
        
        self.moving_obstacles.clear()
        self.obstacle_spawn_timer = 0
        
        for _ in range(20):
            self.spawn_moving_obstacle()
        
        self.drone_move_timer = 0
        self.obstacle_move_timer = 0
        
        self.alert_thread = threading.Thread(target=self.generate_alerts)
        self.alert_thread.daemon = True
        self.alert_thread.start()

    def clear_simulation(self):
        self.simulation_running = False
        if self.alert_thread and self.alert_thread.is_alive():
            self.alert_thread.join()
        
        self.grid = [[EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.hospitals.clear()
        self.buildings.clear()
        self.drones.clear()
        self.moving_obstacles.clear()
        self.active_hospital_drones.clear()
        self.particle_systems.clear()
        
        self.edit_mode = True
        self.selected_type = None
        self.create_alert_file()

    def run(self):
        clock = pygame.time.Clock()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_mouse_event(event)
            
            if self.simulation_running:
                self.update_simulation()
            
            self.draw()
            clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    sim = EnhancedGridSim()
    sim.run()