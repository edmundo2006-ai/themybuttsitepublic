from typing import List, Optional
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Text, text, Enum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime


ItemTypeEnum = Enum('choice', 'required', 'optional', name='item_type_enum')

class Base(DeclarativeBase):
    pass

class Users(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    netid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'consumer'"))
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    orders: Mapped[List['Orders']] = relationship('Orders', back_populates='users')
    cart: Mapped[Optional['Cart']] = relationship('Cart', back_populates='user', uselist=False)

class Settings(Base):
    __tablename__ = 'settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grill_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('TRUE'))
    buttery_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('TRUE'))

class Ingredients(Base):
    __tablename__ = 'ingredients'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('TRUE'))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))

    menu_item_ingredients: Mapped[List['MenuItemIngredients']] = relationship(
        'MenuItemIngredients', back_populates='ingredient'
    )

class MenuItems(Base):
    __tablename__ = 'menu_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    requires_grill: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('FALSE'))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    menu_item_ingredients: Mapped[List['MenuItemIngredients']] = relationship(
        'MenuItemIngredients', back_populates='menu_item', cascade='all, delete-orphan', passive_deletes=True
    )


class MenuItemIngredients(Base):
    __tablename__ = 'menu_item_ingredients'

    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id', ondelete="CASCADE"), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey('ingredients.id', ondelete="CASCADE"), primary_key=True)

    type: Mapped[str] = mapped_column(ItemTypeEnum, nullable=False)
    add_price: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))

    ingredient: Mapped['Ingredients'] = relationship('Ingredients', back_populates='menu_item_ingredients')
    menu_item: Mapped['MenuItems'] = relationship('MenuItems', back_populates='menu_item_ingredients')

class Orders(Base):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    netid: Mapped[str] = mapped_column(ForeignKey('users.netid'))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    specifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    stripe_session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )

    users: Mapped['Users'] = relationship('Users', back_populates='orders')
    order_items: Mapped[List['OrderItems']] = relationship('OrderItems', back_populates='order')

class OrderItems(Base):
    __tablename__ = 'order_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey('orders.id', ondelete='CASCADE')
    )
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey('menu_items.id', ondelete='SET NULL'), nullable=True
    )

    # Snapshot values
    menu_item_name: Mapped[str] = mapped_column(Text, nullable=False)
    menu_item_price: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))

    order: Mapped['Orders'] = relationship(
        'Orders',
        back_populates='order_items',
        passive_deletes=True
    )
    menu_item: Mapped['MenuItems'] = relationship('MenuItems')
    selected_ingredients: Mapped[List['OrderItemIngredient']] = relationship(
        'OrderItemIngredient',
        back_populates='order_item',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

class OrderItemIngredient(Base):
    __tablename__ = 'order_item_ingredients'

    id: Mapped[int] = mapped_column(Integer, primary_key= True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey('order_items.id', ondelete='CASCADE'), nullable= False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey('ingredients.id', ondelete='SET NULL'), nullable=True
    )

    type: Mapped[str] = mapped_column(ItemTypeEnum, nullable=False)

    # Snapshot values
    ingredient_name: Mapped[str] = mapped_column(Text, nullable=False)
    add_price: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))

    order_item: Mapped['OrderItems'] = relationship(
        'OrderItems',
        back_populates='selected_ingredients',
        passive_deletes=True
    )
    ingredient: Mapped['Ingredients'] = relationship('Ingredients')

class Cart(Base):
    __tablename__ = 'carts'

    netid: Mapped[str] = mapped_column(ForeignKey('users.netid'), primary_key=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )
    stripe_session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specifications: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped['Users'] = relationship('Users', back_populates='cart')
    items: Mapped[List['CartItem']] = relationship(
        'CartItem', back_populates='cart', cascade='all, delete-orphan'
    )

class CartItem(Base):
    __tablename__ = 'cart_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_netid: Mapped[str] = mapped_column(ForeignKey('carts.netid'))
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id', ondelete="CASCADE"), nullable=False)

    cart: Mapped['Cart'] = relationship('Cart', back_populates='items')
    menu_item: Mapped['MenuItems'] = relationship('MenuItems')

    selected_ingredients: Mapped[List['CartItemIngredient']] = relationship(
        'CartItemIngredient',
        back_populates='cart_item',
        cascade='all, delete-orphan'
    )

class CartItemIngredient(Base):
    __tablename__ = 'cart_item_ingredients'

    cart_item_id: Mapped[int] = mapped_column(ForeignKey('cart_items.id', ondelete="CASCADE"), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey('ingredients.id', ondelete="CASCADE"), primary_key=True)

    type: Mapped[str] = mapped_column(ItemTypeEnum, nullable=False)

    cart_item: Mapped['CartItem'] = relationship('CartItem', back_populates='selected_ingredients')
    ingredient: Mapped['Ingredients'] = relationship('Ingredients')

    
