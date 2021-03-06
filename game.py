from math import *
from gameconst import *
import mapgen
import collections
from direct.showbase.ShowBase import ShowBase
from direct.showbase import DirectObject
from direct.actor.Actor import Actor
from direct.task import Task
from panda3d.core import *

class GameController():
    """Controller for a bomberman game"""
    VIEWS = {
        'floor': {
            'model': 'assets/plane',
            'texture': 'assets/perlin_noise.jpg',
            'rgba': (0.75, 0.6, 0.5, 1.0),
            'scale': 0.5
        },
        'wall': {
            'model': 'assets/cube',
            'texture': 'assets/metal_texture.jpg',
            'rgba': (0.2, 0.2, 0.2, 1.0),
            'scale': 0.5
        }
    }
    
    def __init__(self, client, width, height, turn_length, map_init, players, me):
        self.client = client
        # init constants for this party
        self.width = width
        self.height = height
        self.turn_length = turn_length
        # build the initial map for the game
        self.map = [[Tile(map_init[y * width + x], x, y, height)
                    for x in xrange(width)] for y in xrange(height)]
        # the list of players
        self.players = [Player(no, xi, yi, height, no == me) for no, (xi, yi) in enumerate(players)]
        # the turn number
        self.turn = 0
        # the no of the player who "I" am
        self.me = me
        # maintain a list of active bombs
        self.bombs = [(x, y, BOMB_COUNTER_INIT)
                      for x in xrange(width) for y in xrange(height)
                      if map_init[y * width + x] == TileContent.BOMB]
        # the bomb to trigger will be added to this queue
        self.to_explode = collections.deque()
        # init the environment
        self.init_world_view()
        # init the keyboard handler
        self.keyboard_handler = ActionKeyHandler(self.client)
    
    def init_world_view(self):
        """Init the 3D world"""
        # set the background color
        # base.setBackgroundColor(0.7, 0.7, 0.7)
        base.setBackgroundColor(0.0, 0.0, 0.0)
        # adjust the camera
        base.disableMouse()
        incline_degrees = 25
        incline_radians = incline_degrees * (pi / 180.0)
        distance = max(self.width, self.height) * 2.25
        camera.setPos((self.width - 1) / 2.0,
            (self.height - 1) / 2.0 - distance * sin(incline_radians),
            distance * cos(incline_radians))
        # camera.setHpr(0, -90, 0)
        camera.setHpr(0, -90 + incline_degrees, 0)
        # set the light
        plight = PointLight('plight')
        intensity = 1.5
        plight.setColor(VBase4(intensity, intensity, intensity, 1.0))
        plnp = render.attachNewNode(plight)
        plnp.setPos((self.width - 1) * 0.25, (self.height - 1) * 0.75, distance)
        render.setLight(plnp)
        
        # floor
        params = self.VIEWS['floor']
        floor = loader.loadModel(params['model'])
        r,g,b,a = params['rgba']
        floor.setColor(r,g,b,a)
        floor.setScale(params['scale'] * (self.width + 2), params['scale'] * (self.height + 2), 1)
        floor.setPos((self.width - 1) / 2.0, (self.height - 1) / 2.0, 0.0)
        if 'texture' in params:
            texture = loader.loadTexture(params['texture'])
            texture.setWrapU(Texture.WMRepeat)
            texture.setWrapV(Texture.WMRepeat)
            floor.setTexture(texture, 1)
        floor.reparentTo(render)
        # walls
        params = self.VIEWS['wall']
        r,g,b,a = params['rgba']
        if 'texture' in params:
            texture = loader.loadTexture(params['texture'])
            texture.setWrapU(Texture.WMRepeat)
            texture.setWrapV(Texture.WMRepeat)
        for i in xrange(self.height + 2):
            # left
            w = loader.loadModel(params['model'])
            w.setColor(r,g,b,a)
            w.setScale(params['scale'])
            w.setPos(-1, i - 1, 0.5)
            if 'texture' in params:
                w.setTexture(texture, 1)
            w.reparentTo(render)
            # right
            w = loader.loadModel(params['model'])
            w.setColor(r,g,b,a)
            w.setScale(params['scale'])
            w.setPos(self.width, i - 1, 0.5)
            if 'texture' in params:
                w.setTexture(texture, 1)
            w.reparentTo(render)
        for i in xrange(self.width):
            # top
            w = loader.loadModel(params['model'])
            w.setColor(r,g,b,a)
            w.setScale(params['scale'])
            w.setPos(i, -1, 0.5)
            if 'texture' in params:
                w.setTexture(texture, 1)
            w.reparentTo(render)
            # bottom
            w = loader.loadModel(params['model'])
            w.setColor(r,g,b,a)
            w.setScale(params['scale'])
            w.setPos(i, self.height, 0.5)
            if 'texture' in params:
                w.setTexture(texture, 1)
            w.reparentTo(render)
        # status text
        text = "alive: " + str(len(self.alive_players()))
        self.client.update_status_text(text)
        
    
    def execute_turn(self, turn_no, actions):
        """Starts a new turn with given turn no and player actions"""
        # update the turn no
        self.turn = turn_no + 1
        # commit the player actions
        self.commit_actions(actions)
        # update the bombs
        self.update_bombs()
        # trigger the explosions
        while self.to_explode:
            xb, yb = self.to_explode.popleft()
            self.trigger_explosion(xb, yb)
        # check the remaining (alive) players in game:
        # if there is only one player remains, he wins the game
        alive_players = self.alive_players()
        if len(alive_players) == 1:
            self.declare_winner(self.players[0])
        # if there is no player left, declare a draw/null
        elif not alive_players:
            self.declare_draw()
        
    
    def declare_winner(self, p):
        """Declare the given player winner"""
        if p == self.players[self.me]:
            text = "You won!"
            self.client.update_status_text(text)
    
    def declare_draw(self):
        """Declare a draw (no winner)"""
        text = "Draw."
        self.client.update_status_text(text)
    
    def commit_actions(self, actions):
        for i, a in enumerate(actions):
            if self.can_do(i, a):
                self.do(i, a)
    
    def alive_players(self):
        """Return the list of players that are not dead"""
        return [p for p in self.players if p.is_alive()]
    
    def can_do(self, player_no, action):
        player = self.players[player_no]
        if player.is_dead():
            return False
        # can a bomb be placed on another one ?
        elif action == Action.POSE_BOMB:
            return (player.has_bomb() and self.map[player.y][player.x].is_free())
        # collision between 2 players ?
        elif action == Action.MOVE_RIGHT:
            return (player.x < self.width - 1 and
                   self.map[player.y][player.x + 1].is_available())
        elif action == Action.MOVE_LEFT:
            return (player.x > 0 and
                   self.map[player.y][player.x - 1].is_available())
        elif action == Action.MOVE_UP:
            return (player.y > 0 and
                   self.map[player.y - 1][player.x].is_available())
        elif action == Action.MOVE_DOWN:
            return (player.y < self.height - 1 and
                   self.map[player.y + 1][player.x].is_available())
        else:
            return True
    
    def do(self, player_no, action):
        player = self.players[player_no]
        if action == Action.POSE_BOMB:
            player.take_bomb()
            self.add_bomb(player.x, player.y)
        elif action in [Action.MOVE_RIGHT, Action.MOVE_LEFT, Action.MOVE_UP, Action.MOVE_DOWN]:
            player.move(action, self.turn_length)
    
    def add_bomb(self, x, y):
        self.map[y][x].put_bomb()
        self.bombs.append((x, y, BOMB_COUNTER_INIT))
    
    def update_bombs(self):
        """Update the bomb counters and trigger explosions accordingly"""
        # decrement counters
        self.bombs = [(xb, yb, ib - 1) for xb, yb, ib in self.bombs]
        # add to to_explode every bomb whose counter is zero
        for xb, yb, ib in self.bombs:
            if ib <= 0:
                self.to_explode.append((xb, yb))
    
    def trigger_explosion(self, xb, yb):
        """Start a bomb explosion event at (xb, yb)."""
        # destroy the bomb and remove it from the list of active bombs
        self.map[yb][xb].destroy()
        self.bombs = [(x, y, i) for (x, y, i) in self.bombs if (x != xb or y != yb)]
        
        # kill any player on the tile where the bomb explodes
        for p in self.alive_players():
            if p.x == xb and p.y == yb:
                self.kill(p)
        # explosion to the right
        for (x, y) in [(xb + i, yb) for i in xrange(1, BOMB_RADIUS + 1) if xb + i < self.width]:
            t = self.map[y][x]
            # kill any player within the explosion radius
            for p in self.alive_players():
                if p.x == x and p.y == y:
                    self.kill(p)
            # destroy any destructible block within the radius
            if t.content == TileContent.SOFT_BLOCK:
                t.destroy()
            # add any bomb within the radius to a list of bombs to explode
            elif t.content == TileContent.BOMB:
                self.to_explode.append((x, y))
            # stop the explosion if an indestructible block blocks it
            elif t.content == TileContent.HARD_BLOCK:
                break
        # explosion to the left
        for (x, y) in [(xb - i, yb) for i in xrange(1, BOMB_RADIUS + 1) if xb - i >= 0]:
            t = self.map[y][x]
            # kill any player within the explosion radius
            for p in self.alive_players():
                if p.x == x and p.y == y:
                    self.kill(p)
            # destroy any destructible block within the radius
            if t.content == TileContent.SOFT_BLOCK:
                t.destroy()
            # add any bomb within the radius to a list of bombs to explode
            elif t.content == TileContent.BOMB:
                self.to_explode.append((x, y))
            # stop the explosion if an indestructible block blocks it
            elif t.content == TileContent.HARD_BLOCK:
                break
        # upward explosion
        for (x, y) in [(xb, yb - i) for i in xrange(1, BOMB_RADIUS + 1) if yb - i >= 0]:
            t = self.map[y][x]
            # kill any player within the explosion radius
            for p in self.alive_players():
                if p.x == x and p.y == y:
                    self.kill(p)
            # destroy any destructible block within the radius
            if t.content == TileContent.SOFT_BLOCK:
                t.destroy()
            # add any bomb within the radius to a list of bombs to explode
            elif t.content == TileContent.BOMB:
                self.to_explode.append((x, y))
            # stop the explosion if an indestructible block blocks it
            elif t.content == TileContent.HARD_BLOCK:
                break
        # downward explosion
        for (x, y) in [(xb, yb + i) for i in xrange(1, BOMB_RADIUS + 1) if yb + i < self.height]:
            t = self.map[y][x]
            # kill any player within the explosion radius
            for p in self.alive_players():
                if p.x == x and p.y == y:
                    self.kill(p)
            # destroy any destructible block within the radius
            if t.content == TileContent.SOFT_BLOCK:
                t.destroy()
            # add any bomb within the radius to a list of bombs to explode
            elif t.content == TileContent.BOMB:
                self.to_explode.append((x, y))
            # stop the explosion if an indestructible block blocks it
            elif t.content == TileContent.HARD_BLOCK:
                break
    
    def kill(self, player):
        """Kill the given player."""
        # trigger the death of the player
        player.die()
        # update the status text
        text = "alive: " + str(len(self.alive_players()))
        self.client.update_status_text(text)
        # if the player was me, disable the keyboard handler (stop sending actions)
        if player == self.players[self.me]:
            self.keyboard_handler.destroy()
            self.keyboard_handler = None
            text = "You lose!"
            self.client.update_status_text(text)
        # (keep the player in the list of players but keep him dead)
        
    

class Player(object):
    """In-game model for a player"""
    VIEWS = {
        0: {
            'model': 'assets/cone_actor',
            'rgba': (1.0, 0, 0, 1.0),
            'scale': 0.5
        },
        1: {
            'model': 'assets/cone_actor',
            'rgba': (0, 1.0, 0, 1.0),
            'scale': 0.5
        },
        2: {
            'model': 'assets/cone_actor',
            'rgba': (0, 0, 1.0, 1.0),
            'scale': 0.5
        },
        3: {
            'model': 'assets/cone_actor',
            'rgba': (1.0, 1.0, 0, 1.0),
            'scale': 0.5
        },
        'me_marker': {
            'model': 'assets/sphere',
            'scale': 0.33,
            'pos': Point3(0.0, 0.0, 1.33)
        }
    }
    
    def __init__(self, no, xi, yi, height, me=False):
        super(Player, self).__init__()
        # player number
        self.no = no
        # initial position
        self.x = xi
        self.y = yi
        self.height = height
        # boolean flag, False if the player is dead
        self.alive = True
        # the last interval action will be stored there
        # so that we can finish it prematurely  if a new one is to be executed
        self.last_action = None
        # load the corresponding view
        params = self.VIEWS[no % 4]
        self.view = Actor(params['model'])
        # self.view = loader.loadModel(self.VIEWS[no]['model'])
        if 'rgba' in params:
            r,g,b,a = params['rgba']
            self.view.setColor(r,g,b,a)
        if 'scale' in params:
            self.view.setScale(params['scale'])
        self.view.setPos(xi, height - yi - 1, 0.5)
        self.view.reparentTo(render)
        # if the player is "Me", put the me marker to show him
        if me:
            params = self.VIEWS['me_marker']
            marker = loader.loadModel(params['model'])
            if 'scale' in params:
                marker.setScale(params['scale'])
            if 'pos' in params:
                marker.setPos(params['pos'])
            marker.reparentTo(self.view)

    def move(self, action, time):
        """Move the player towards the given direction."""
        if action == Action.MOVE_RIGHT:
            self.x += 1
        elif action == Action.MOVE_LEFT:
            self.x -= 1
        elif action == Action.MOVE_UP:
            self.y -= 1
        elif action == Action.MOVE_DOWN:
            self.y += 1
        if self.last_action: self.last_action.finish()
        self.last_action = self.view.posInterval(time / 1000.0, Point3(self.x, self.height - self.y - 1, 0.5))
        self.last_action.start()
        # self.view.posInterval(time / 1000, Point3(self.x, self.y, 0)).start()
    
    def has_bomb(self):
        return True
    
    def take_bomb(self):
        pass
    
    def die(self):
        """Trigger the death of the player"""
        self.alive = False
        self.view.delete()
        self.view.removeNode()
        self.view = None
    
    def is_alive(self):
        return self.alive
    
    def is_dead(self):
        return not self.alive

class Tile(object):
    """In-game model for a tile"""
    VIEWS = {
        TileContent.SOFT_BLOCK: {
            'model': 'assets/cube',
            'texture': 'assets/perlin_noise.jpg',
            'rgba': (0.5, 0.5, 0.5, 1.0),
            'scale': 0.5
        },
        TileContent.HARD_BLOCK: {
            'model': 'assets/cube',
            'texture': 'assets/metal_texture.jpg',
            'rgba': (0.2, 0.2, 0.2, 1.0),
            'scale': 0.5
        },
        TileContent.BOMB: {
            'model': 'assets/sphere',
            'rgba': (0.8, 0.1, 0.1, 1.0),
            'scale': 0.5
        }
    }
    
    def __init__(self, content, x, y, height):
        super(Tile, self).__init__()
        # the tile's content
        self.content = content
        # the tile's position
        self.x = x
        self.y = y
        self.height = height
        # load the corresponding view and place it in the correct position
        if not content == TileContent.FREE:
            self.view = self.load_view(content)
            self.view.setPos(x, height - y - 1, 0.5)
            self.view.reparentTo(render)
        else:
            self.view = None
    
    def load_view(self, content):
        """Load and return the view for the given content"""
        params = self.VIEWS[content]
        view = loader.loadModel(params['model'])
        if 'texture' in params:
            view.setTexture(loader.loadTexture(params['texture']))
        if 'rgba' in params:
            r,g,b,a = params['rgba']
            view.setColor(r,g,b,a)
        if 'scale' in params:
            view.setScale(params['scale'])
        return view
    
    def is_available(self):
        """Return True if this tile can be crossed by a player."""
        return (self.content == TileContent.FREE or self.content == TileContent.BOMB)
        
    def is_free(self):
        """Return True a player can pose a bomb on this tile."""
        return (self.content == TileContent.FREE)
    
    def put_bomb(self):
        """Put a new bomb on this Tile"""
        if self.view: self.view.removeNode()
        self.content = TileContent.BOMB
        self.view = self.load_view(self.content)
        self.view.setPos(self.x, self.height - self.y - 1, 0)
        self.view.reparentTo(render)
    
    def destroy(self):
        """Destroy this tile, making it a free tile"""
        if not self.content == TileContent.FREE:
            self.content = TileContent.FREE
            self.view.removeNode()
            self.view = None

class ActionKeyHandler(DirectObject.DirectObject):
    def __init__(self, client):
        # keep reference to the client in order to trigger the packet send
        self.client = client
        # init the handler to send the actions corresponding to the key pressed
        self.accept('x', self.send_action, [Action.POSE_BOMB])
        self.accept('arrow_up', self.send_action, [Action.MOVE_UP])
        self.accept('arrow_up-repeat', self.send_action, [Action.MOVE_UP])
        self.accept('arrow_down', self.send_action, [Action.MOVE_DOWN])
        self.accept('arrow_down-repeat', self.send_action, [Action.MOVE_DOWN])
        self.accept('arrow_right', self.send_action, [Action.MOVE_RIGHT])
        self.accept('arrow_right-repeat', self.send_action, [Action.MOVE_RIGHT])
        self.accept('arrow_left', self.send_action, [Action.MOVE_LEFT])
        self.accept('arrow_left-repeat', self.send_action, [Action.MOVE_LEFT])

    def send_action(self, action):
        self.client.send_action_request(action)

    def destroy(self):
        """Get rid of this handler"""
        self.ignoreAll()
