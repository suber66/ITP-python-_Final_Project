# physics/__init__.py
# ИСПРАВЛЕНИЕ: Оба имени теперь берутся из одного источника.
# Старый physics/layers.py больше не нужен — его можно удалить.
from physics.physicsManager import PhysicsLayers, PhysicsManager

__all__ = ['PhysicsLayers', 'PhysicsManager']
