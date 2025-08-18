# Documentation


## Overview

The MY Buttsite is a web application designed to streamline buttery operations at Yale's Pauli Murray College. It allows customers to browse menus, place orders, and track updates while allowing buttery staff to manage orders, inventory, and menu items efficiently.


## Setup Guide

In order to use The MY Buttsite, it is required that the following libraries are installed prior to running the program: Flask, flask-socketio, Werkzeug, cs50, Flask-Cors, and Flask-Mail.

In order to do this, follow the following setup steps:
1. Make sure to download the project's zip file (project.zip).
2. Unzip the project by running unzip project.zip in the terminal.
3. Run cd project on the terminal.
4. Install all dependencies by running pip install -r requirements.txt on the terminal.
5. Run the application by running python app.py on the terminal
6. Open the website when prompted at the bottom right corner.

## Creating an Account

### Customer Account
There are two options for creating an account: one for customers and one for buttery staff members. To make either one of these, it is necessary to click the text "Don't have an account? Register here", which will redirect you to the registration page. If the user is a customer, the username can attempt to create an account by entering a unique username and password and by confirming such password. If the user name is taken when creating the account, the user will be notified at the top of their screen. If the user successfully creates their account, they will be notified of doing so at the middle top of their screen and will be redirected to the login page.

### Staff Account
If the user is a Buttery staff member, they will go through the same procedure as the customer. However, they will select the "Register as Buttery Staff" checkbox. Doing so will display a text box in which the staff member has to put in a secret key. The secret key is **GRILLED_cheeseMYBUTT24**. If a user, not a buttery staff member, tries to create an account and uses the incorrect key, they will not be allowed to do so and will be notified by the program that the secret key is not correct. Once the secret key is in, the buttery staff member may create their account and be redirected to the login page.

## Customer Guide

### Viewing the Menu
The user may log in using their username and password if the user is a customer. Doing so will redirect the user to the buttery page. On the buttery page, the customer will be able to utilize a navigation bar at the top to direct them to different sections of the page. However, it is not necessarily needed, and the customer can scroll down the page to view its contents. One of the first things the customer will see is the buttery status and grill status. These options allow the customer to decide whether to buy food from the buttery. If the grill is closed, those items that require the use of the grill (i.e. chicken quesadilla) will not appear on the menu. If the buttery is closed, the customer can see the menu items. However, if they try to check out, they will not be allowed to do so.
If the customer scrolls farther down, they will see the menu. This menu includes all of the menu items that are currently available. The customer may select the ingredients they would like on their order but remember that they must select at least one ingredient, and they cannot choose ingredients that are out of stock. If an ingredient is out of stock, the customer will see a red text following the ingredient that says "Out of Stock." Once the ingredients have been selected using the checkboxes, the customer may click the green "Add to Cart" button. Once this is done, the user should see a message that says their item has been successfully added to their cart. If they scroll up to the navigation bar, they will also see that the View Cart item has increased by one.

### Viewing Orders
If the customer scrolls farther down, they will see the orders they have made. If they have not made any orders, they will see a message saying, "You have no orders at the moment." Once the customer decides to make an order, they can see the order ID, items, status, and the last time the order was updated on a table. Suppose the customer decides to stay on the website. In that case, they will eventually be notified that their order's status has changed from "Pending" to "Ready," or vice versa if a buttery staff member does update their order. They will also see the change reflected in the table.

### Additional Information
If the customer keeps scrolling down on the same page, they will see additional information, such as the hours and days the buttery is open and the buttery's social media.

### Cart Functionalities
A customer can view their cart in two different ways. They may view it by clicking on the navigation bar item that says View Cart, or they could scroll down and see a blue button that says View Cart between the menu and the order sections. Clicking either button has the same functionality. Once this button is clicked, the customer is redirected to the cart page. If the customer has no items on their cart, they will see the message "Your cart is empty." Clicking the blue button will redirect them back to the buttery page. If the customer does have at least one item on their cart, they will see an order summary that displays information such as the item, the price, and the ingredients. In addition, the customer can also add specifications to specific items for special instructions given to the buttery staff. For these instructions to be saved, the customer must type in their specifications and then click the blue button that says update, which will save the specifications. If the user no longer wishes to have a specific menu item, they may remove it by clicking on the red " Remove " button.

### Selecting Payment Method/Delivery
The customer is also able to select different ways to pay and receive their order. The only combination that is not allowed is to pay at the buttery and also get the order delivered to the dorm. If the user selects the "Get it delivered to your dorm (extra cost)" option for delivery, they must input their entryway and suite/room number. The user can only proceed if these two requirements have been fulfilled.

### Proceeding to Check Out
The user is also able to see a price breakdown of their order at the bottom of the page. If the user selects their order to be delivered to their dorm, they will also see an entry that says "Delivery Fee - $ 3.00", and that cost is also factored in the total price. If the user is ready to checkout, they may click on the green button that says "Proceed to Checkout." Some things to keep in mind are that if a user had added an item that requires a grill beforehand and tries to checkout with the item when the grill is closed, they will be redirected to the buttery page, and they will be asked to remove the item from their cart before proceeding to checkout. If there are no errors, such as missing selections, clicking the button will redirect the user to the checkout page.

### Checkout Page
On the checkout page, the user will be able to see their final order summary with specifications, entryway, and room/suite number if the order is being delivered. In addition, if the user selects to pay for their order at the buttery, they will only be asked to enter their email address. If they choose to pay online, they will also be asked to enter their payment details (for this project, this feature is not real so that the user can input anything without any repercussions). Once this has been filled out, the user can attempt to checkout. If everything is successful, the user will be redirected to the buttery page, where they will see success messages at the top of their screen. The user may also check their email address to see their order confirmation (Note: emails tend to end up in the "Spam" folder, so be sure to check here, too). Once the user has checked out, the user can scroll down to view their order(s).

## Staff Guide

### Buttery/Grill Statuses
If a staff member logs into their account, they will redirected to the staff page. On this page, they will be able to do several things. The first thing they will see is the status of the buttery. They will have the ability to use two buttons: One which opens/closes the buttery and the other one which opens/closes the grill. When the buttery is closed, no more orders will be received; when the grill is closed, only orders that do not require the use of the grill will be accepted.

### Orders
If the staff member scrolls down, they will see a table with all the orders alongside their information. If a buttery staff member is done preparing an order, they may click on the dropdown box on the status column of a specific order and choose the "Done" option. They must then select Update to record the change. If needed, the staff member may also do vice versa with the "Pending" option. There is no need for the staff member to refresh the page to receive new orders, as the incoming orders are appended at the end of the table. Nonetheless, refreshing the page also works in displaying new orders.

### Ingredients
The staff member can also set certain ingredients out of stock if they run out. They can look for the ingredient, click the dropdown menu, select "Out of Stock," and click the blue "Update" button. Customers will notice this change, as the ingredients that are out of stock will have a message that says so next to them. If the staff member decides to put an ingredient back in stock, they do the same process, except that they choose "In Stock" this time.

### Editing Menu
Staff members can keep scrolling down, and they will see that they can manage the menu. The menu is viewed in a carousel. It is used by clicking on the sides of the carousel, which will switch the item to the previous/next one. Staff members can update items' names, prices, and descriptions. They must fill out the entries on the screen and click on the blue " Update " button once they finish the changes. In addition, they can delete specific menu items by clicking on the red "Delete" button.

### Adding Menu Items
At the end of the page, the staff member will see they can add items to the menu. To do so, they can fill out the forms that ask for the name, price, and description. In addition, they will have to choose all the ingredients that customers may select for this menu item. To do so, they can hold Ctrl (on Windows) or Command (on Mac) to choose multiple ingredients. Staff members can only add a menu item if they select at least one ingredient.


## Logging out

Users may log out by using the red "Logout" button at the top right of the staff page and at the navigation bar on the buttery page. For customers, information such as the current cart and orders are saved even after logging out or closing the website—the same works for staff members for orders.

## Youtube URL
https://www.youtube.com/watch?v=5SVGYSIsEo4
