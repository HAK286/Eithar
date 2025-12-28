const express = require('express');
const http = require('http');
const socketIo = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = socketIo(server);

// Serve static files (e.g., your HTML, CSS, JS files)
app.use(express.static('public'));

// Socket.IO connection
io.on('connection', (socket) => {
    console.log('New client connected');

    // Listen for incoming messages
    socket.on('send_message', (message) => {
        io.emit('receive_message', message); // Broadcast the message to all clients
    });

    // Handle disconnect
    socket.on('disconnect', () => {
        console.log('Client disconnected');
    });
});

// Start the server
server.listen(3000, () => {
    console.log('Server is running on port 3000');
});
