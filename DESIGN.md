# Design

## Technology Stack

### Frontend
- HTML/CSS/JavaScript: I used these languages to create the user interface. The templates are dynamically rendered using Flask's Jinja2 templating engine.
- Bootstrap: I integrated Bootstrap to make the website more responsive to changes, especially for different devices. I also used it for styling and to create different sections. In addition, I used the navbar feature to implement the navigation bar.

### Backend
- Flask: This is the main framework I used for the website.
- Flask-SocketIO: I implemented this library because it enabled me to send real-time updates for order status changes. This also allowed me to update the staff's orders table without refreshing the page.
- CS50 Library: I used this library to use the SQLite database, which was used to store information such as user accounts, orders, menu items, and inventory data.

### Other Important Libraries
- Werkzeug: I used this library to hash passwords and keep them secured in the database
- Flask-Cors: It was used to allow cross-origin requests, which ensures that interaction between different platforms will be smooth.
- Flask-Mail: I implemented this to send email confirmations for orders.

## Database Design

My project relies heavily on databases and how information is stored and related to one another. Here is a brief overview of what my database design looks like.

1. Users table: It includes an ID in order to identify each user uniquely. It also consists of a username field, which has to be unique, meaning that there cannot be two users with the same username. The passwords are stored in their hashed form, preventing anyone from accessing the database and getting everyone's password. Finally, it includes a role that defaults to 'consumer' unless the account is created by inputting the secret key for buttery staff. Adding this role allows me to ensure specific functionality is only accessible to staff members.
2. Ingredients table: Again, it uses a unique ID which can be used to identify each ingredient. It also includes a name and a Boolean field that indicates its availability. I did this because keeping the ingredients' stock status in their own table provided me with flexibility in updating and querying ingredient data independently of menu items.
3. Menu Items table: Each item has a unique ID to be able to identify it. It includes fields such as the name, price, description of the item, image URL, and Boolean field that indicates whether the item needs a grill for preparation. Adding the Boolean field allows for conditional filtering of menu items based on grill availability, improving user experience.
4. Menu Item Ingredients table: This table consists of two main fields: the menu item ID and the ingredients ID. This many-to-many relationship table allows me to connect the menu items to their ingredients using foreign keys for references. This makes this database more scalable in case newer ingredients or menu items exist.
5. Settings table: This table stores only one row with two columns: One for the grill being open/closed and the other for the butter being open/closed. By having this table, I can ensure consistency throughout the program regarding whether someone can check out certain items and change the menu for customers.
6. Orders table: This table assigns each order a unique ID. In addition, it stores different information such as the user's ID, email, delivery option (only pick_up and deliver_to_dorm are valid values), total price, status (defaults to pending and used to track order progress), timestamp, and entryway and suite/room number if the delivery option is to deliver to the dorm.
7. Order Items table: This table uses the order_id foreign key from the Orders table in order to show information about orders, such as the name(s) of the items ordered, the price of each, the specifications, if any, and the ingredients selected for each item. This ensures historical accuracy even if menu items are updated or removed.

Most of the website functions by running queries (i.e. the menu is displayed based on whether the grill is open or not). Orders are also stored in the database and displayed dynamically. However, these do not necessarily need the page to be refreshed to be displayed. Look at the **Real-Time Updates in the website** section for more.

## User Authentication

Only logged-in users can access certain features using a login_required decorator. This decorator checks if a user's user_id is stored in the session. If not, it redirects them to the login page with a warning message. Passwords are hashed with Werkzeug for extra security, ensuring they're never stored in plain text.

## Role-Based Access Control

Access to certain features is limited based on user roles, like customers or staff. These roles are saved in the database and are assigned at the time of registration. If a user wants to be a part of the role "staff," they have to be able to input the correct secret key for the role to be given to them. The website uses the role_required decorator, which checks the user's role stored in the session. If the role doesn't match the required one, the user is redirected and shown an error message. Staff can do things like update menu items, while customers see only customer-specific options. This separation keeps the system organized and secure.

## Cart Functionality

The cart functionality uses Flask's built-in session to store shopping data temporarily as client-side cookies, making it efficient without needing a database for cart storage. Each cart item is saved as a dictionary with details like ID, name, price, and selected ingredients. When an item is added, the backend validates that at least one ingredient is selected and checks their stock using SQL queries against the ingredients table. The session is updated dynamically, with changes tracked using session.modified to ensure the data stays current. Removing items involves searching through the session's cart and deleting the matching item, with the session reflecting the update immediately. The total cost, including optional delivery fees, is recalculated on the fly based on the items in the cart. During checkout, delivery and payment details are validated, and once the order is placed, the session is cleared to keep things secure and prevent leftover data.

## Menu Customization

Customers can customize their orders by choosing ingredients for each menu item, making their experience more personal. The website checks the in_stock status of ingredients from the database and marks any that are unavailable so customers can't select them. This avoids problems during order preparation and ensures accuracy. Staff can update ingredient availability using a simple tool that changes the in_stock status in the database. This keeps the menu up-to-date and ensures only available ingredients are shown to customers.

## Order Management

### Database Usage
My website's order management system is centered around two main database tables: orders and order_items. The orders table stores general details about each order, such as the unique order_id, the user who placed the order (user_id), the total price, the delivery option (i.e., "pick up" or "deliver to dorm"), and timestamps. Additional fields like entryway and room_number are also saved if the order includes delivery. The order_items table stores information about each item in an order, including the item's name, price, any customizations (like "no onions"), and selected ingredients. Each entry in order_items is linked to the corresponding entry in orders through the order_id.

### Orders with Multiple Items
When a customer places an order, the main order details are saved in the orders table, and separate entries are created for each cart item in the order_items table. This structure ensures that each item's details are stored individually while still tied to a single order. For example, if a user orders a BEC sandwich with custom ingredients and a drink, both items are saved as separate rows in order_items but share the same order_id.

### Viewing Past Orders
Customers can view their past orders on the buttery page. The backend queries the orders and order_items tables, groups the items by order_id, and presents the data in a clear format. Each order includes a list of items, their customizations, and the order status. This makes it easy for customers to track their orders.

### Staff Managing Orders
Staff manage orders through the staff management page, which pulls all orders from the database and groups them by order_id. For each order, staff can see the customer's details, the list of ordered items with their customizations, and any required delivery information. Staff can modify the orders table to update orders by marking them as "Done" in the database.

## Sending Emails

The website uses Flask-Mail to send order confirmation emails to customers after they place an order. When an order is submitted, the backend creates an email using the Message class, including details like the subject ("Order Confirmation"), the recipient's email address, and the order details. The content of the email is generated using an HTML template (email_summary.html), which is filled with information about the order, such as the items, total price, and delivery details. The backend connects to Gmail's SMTP server using the configured email credentials to send the email securely (For this project, I created an account to send the emails). If the email is sent successfully, the customer receives a detailed confirmation. The website notifies the user if there is an exception, such as a connection issue.

## Real-Time Updates in the Website

### Quick Overview
The website uses Flask-SocketIO, which enables real-time updates through the creation of rooms. Look at the following examples to see how it works.

### Customer Logistics
Users who log in are automatically added to a unique "room" on the server based on their user_id. This room is a channel for the server to send messages specifically to that user. For example, when staff updates the status of an order, such as marking it as "Done," the server sends a notification to the corresponding user's room. The frontend receives the update, and the user's page then updates instantly using JavaScript without reloading the page. Through these scripts, the user is notified that their order status has changed, and the change is reflected in their orders table.

### Staff Logistics
Staff members join a shared room called staff_updates, which allows the server to send notifications about all new orders. Whenever a customer places an order, the server sends the order details to this room. Staff pages listening to this room immediately display the new order by appending a new row to the orders table using JavaScript. This is particularly helpful because it allows staff to view orders without continuously reloading the page to check for new orders.

