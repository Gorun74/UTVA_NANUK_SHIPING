from sqlalchemy import Column, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = 'cases'

    sku = Column(Text, primary_key=True)
    upc = Column(Text)
    old_item_number = Column(Text)
    description = Column(Text)
    us_map_price = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    dim_interior = Column(Text)
    dim_exterior = Column(Text)
    int_length_mm = Column(Float, nullable=True)
    int_width_mm = Column(Float, nullable=True)
    int_height_mm = Column(Float, nullable=True)
    ext_length_mm = Column(Float, nullable=True)
    ext_width_mm = Column(Float, nullable=True)
    ext_height_mm = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    reorder_point = Column(Integer, default=3)

    stock_record = relationship('Stock', back_populates='item', uselist=False, cascade='all, delete-orphan')
    container_lines = relationship('ContainerLine', back_populates='item')
    sale_lines = relationship('SaleLine', back_populates='item')
    fifo_lots = relationship('FifoLot', back_populates='item')


class Container(Base):
    __tablename__ = 'containers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_ordered = Column(Text)
    used_rate = Column(Float)
    shipping_aud = Column(Float, default=0.0)
    other1_aud = Column(Float, default=0.0)
    other1_label = Column(Text, default='Other 1')
    other2_aud = Column(Float, default=0.0)
    other2_label = Column(Text, default='Other 2')
    expected_arrival_date = Column(Text)
    date_received = Column(Text)
    status = Column(Text, default='ordered')
    container_size = Column(Text, default='20ft')
    container_fill = Column(Text, default='full')

    total_cbm = Column(Float, nullable=True)
    ship_ocean_aud = Column(Float, nullable=True)
    ship_extras_aud = Column(Float, nullable=True)
    ship_insurance_aud = Column(Float, nullable=True)
    ship_duty_aud = Column(Float, nullable=True)
    ship_gst_aud = Column(Float, nullable=True)
    ship_total_aud = Column(Float, nullable=True)

    lines = relationship('ContainerLine', back_populates='container', cascade='all, delete-orphan')
    fifo_lots = relationship('FifoLot', back_populates='container')
    sale_allocations = relationship('SaleAllocation', back_populates='container')


class ContainerLine(Base):
    __tablename__ = 'container_lines'

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(Integer, ForeignKey('containers.id'))
    sku = Column(Text, ForeignKey('cases.sku'))
    qty_ordered = Column(Integer)
    qty_received = Column(Integer, default=0)
    unit_price_usd = Column(Float, nullable=True)

    container = relationship('Container', back_populates='lines')
    item = relationship('Item', back_populates='container_lines')


class Stock(Base):
    __tablename__ = 'stock'

    sku = Column(Text, ForeignKey('cases.sku'), primary_key=True)
    qty_on_hand = Column(Integer, default=0)

    item = relationship('Item', back_populates='stock_record')


class Sale(Base):
    __tablename__ = 'sales'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_sold = Column(Text)
    channel = Column(Text)
    current_rate = Column(Float)

    lines = relationship('SaleLine', back_populates='sale', cascade='all, delete-orphan')


class SaleLine(Base):
    __tablename__ = 'sale_lines'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey('sales.id'))
    sku = Column(Text, ForeignKey('cases.sku'))
    qty = Column(Integer)
    sell_price_aud = Column(Float)
    cogs_aud = Column(Float, nullable=True)
    cogs_usd_equiv = Column(Float, nullable=True)
    fx_gain_loss = Column(Float, nullable=True)

    revenue_aud = Column(Float, nullable=True)
    gross_profit_aud = Column(Float, nullable=True)
    gross_margin_pct = Column(Float, nullable=True)
    ship_cost_per_unit_aud = Column(Float, nullable=True)
    ship_cost_sale_aud = Column(Float, nullable=True)
    duty_per_unit_aud = Column(Float, nullable=True)
    net_profit_aud = Column(Float, nullable=True)
    net_margin_pct = Column(Float, nullable=True)
    total_return_aud = Column(Float, nullable=True)

    sale = relationship('Sale', back_populates='lines')
    item = relationship('Item', back_populates='sale_lines')
    allocations = relationship('SaleAllocation', back_populates='sale_line', cascade='all, delete-orphan')


class SaleAllocation(Base):
    __tablename__ = 'sale_allocations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey('sales.id'))
    sale_line_id = Column(Integer, ForeignKey('sale_lines.id'))
    container_id = Column(Integer, ForeignKey('containers.id'))
    sku = Column(Text, ForeignKey('cases.sku'))
    qty = Column(Integer)
    revenue_aud = Column(Float, nullable=True)
    cogs_aud = Column(Float, nullable=True)
    net_profit_aud = Column(Float, nullable=True)

    sale_line = relationship('SaleLine', back_populates='allocations')
    container = relationship('Container', back_populates='sale_allocations')


class FifoLot(Base):
    __tablename__ = 'fifo_lots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(Integer, ForeignKey('containers.id'))
    sku = Column(Text, ForeignKey('cases.sku'))
    qty_remaining = Column(Integer)
    landed_cost_aud_per_unit = Column(Float)
    used_rate = Column(Float)
    ship_cost_per_unit_aud = Column(Float, nullable=True)
    duty_per_unit_aud = Column(Float, nullable=True)

    container = relationship('Container', back_populates='fifo_lots')
    item = relationship('Item', back_populates='fifo_lots')
