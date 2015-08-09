

// TODO:
// - load 5s. after completing, not setInterval
// - testcases
// - tidy replay option
// - timezone offset checking
// - pre-define transition.duration(750).ease('cubic-in') ?

// Constants
var MONEY_FORMAT = '$0,0.00';
var binned_datetime_format = d3.time.format('%Y-%m-%d %H:%M:%S');
var point_datetime_format = d3.time.format('%Y-%m-%dT%H:%M:%S+00:00')
var default_animation = d3.transition().duration(750).ease('cubic-in');
var spinner = {height: 50, width: 50};

// Variables
var replay = {
    start_server: null,
    start_client: null,
    speedup: 0 // frozen in time
}
var cached_data = null;
var first_render = true;

var graphs = { 
    running_total: {
        selector: 'svg#running_total',
        x: d3.time.scale(),
        y: d3.scale.linear(),
        svg: null,
        xAxis: d3.svg.axis(),
        yAxis: d3.svg.axis(),
        margin: { top: 20, right: 20, bottom: 30, left: 60},
        drawn_data_points: 0,
        interpolation: 'bundle', // bundle? step-before? basis? monotone?
        yAxisMaxStepSize: 100000,
        crossbar_threshold: 50000, // Events within this amount will show up as crossbar
        crossbar_marin: { left: 7, right: 7 }
    },
    bar_hourly_count: {
        selector: 'svg#bar_hourly_count',
        x: d3.time.scale(),
        y: d3.scale.linear(),
        svg: null,
        xAxis: d3.svg.axis(),
        yAxis: d3.svg.axis(),
        margin: { top: 20, right: 20, bottom: 30, left: 60},
    },
    bardistribution: {
        selector: 'svg#bardist',
        x: d3.scale.linear(),
        y: d3.scale.linear(),
        svg: null,
        xAxis: d3.svg.axis(),
        yAxis: d3.svg.axis(),
        margin: { top: 20, right: 20, bottom: 30, left: 60},
    }
}

graphs.bar_hourly_count.height = 250 - graphs.bar_hourly_count.margin.top - graphs.bar_hourly_count.margin.bottom;
graphs.running_total.height = 250 - graphs.running_total.margin.top - graphs.running_total.margin.bottom;


// running_total


var number_mapping = [
    // [DOM id, JSON name],
    ['#donations_amount', 'amount', MONEY_FORMAT],
    ['#donations_max', 'max', MONEY_FORMAT],
    ['#donations_avg', 'avg', MONEY_FORMAT],
    ['#donations_count', 'count', '0'],
];

function update_sizes() {
    _update_sizes(graphs.running_total);
    _update_sizes(graphs.bar_hourly_count);
    _update_sizes(graphs.bardistribution);
}
function _update_sizes(scope) {
    // Called every time the window and thus potentially the graphs change in size
    scope.width = $(scope.selector).width() - scope.margin.left - scope.margin.right;
    scope.height = $(scope.selector).height() - scope.margin.top - scope.margin.bottom;
    var spinners = d3.selectAll(scope.selector + ' .loading');
    if (first_render) {
        spinners = spinners.attr('opacity', '1') // Insta-show, now animation
    } else {
        spinners = spinners.transition().duration(750) // animated
    }
    spinners.attr('transform', 'translate(' + (scope.width - spinner.width) / 2 + ',' + (scope.height - spinner.height) / 2 + ')');
    scope.x.range([0, scope.width]);
    scope.y.range([scope.height, 0]);
    scope.xAxis.scale(scope.x);
}

function load() {
    $('#refresh_graph').text('Loading...').attr('disabled', true);
    var data_url = SOURCE;
    if (replay.start_server) {
        var replay_up_to = replay.start_server + ((new Date() - replay.start_client) / 1000 * replay.speedup);
        data_url = data_url + '?replay=' + replay_up_to;
    }
    d3.json(data_url, function(error, data) {
        $('#refresh_graph').text('Refresh').attr('disabled', false);
        if (error) {
            return console.warn(error);
        };
        // Converting some values
        if (data.event) {
            data.bar_hourly_count.data.forEach(function(d) { d.moment_parsed = binned_datetime_format.parse(d.moment) });
            data.bar_hourly_count.meta.start_parsed = point_datetime_format.parse(data.bar_hourly_count.meta.start);
            data.bar_hourly_count.meta.end_parsed = point_datetime_format.parse(data.bar_hourly_count.meta.end);
            data.running_total.forEach(function(d) { d.moment_parsed = binned_datetime_format.parse(d.moment) });
            data.event.start_parsed = point_datetime_format.parse(data.event.start);
            data.event.end_parsed = point_datetime_format.parse(data.event.end);

            number_mapping.forEach(function(mapping) {
                var domid = mapping[0];
                var jsonid = mapping[1];
                var format = mapping[2];
                var old_value = $(mapping[0]).attr('data-num-value');
                var new_value = data.aggregated[jsonid];
                if (old_value != new_value) {
                    // The following tween will do two things:
                    //   [1] It updates 'data-num-value' to the numerical value
                    //   [2] it sets the textCotent to a formatted version
                    d3.select(domid).transition().duration(750).attrTween('data-num-value', function() {
                        var domelem = this;
                        var ifunc = d3.interpolate(old_value, new_value);
                        return function(t) {
                            var between_value = ifunc(t);
                            domelem.textContent = numeral(between_value).format(format); // [2]
                            return between_value; // [1]
                        };
                    });
                };
            });
        }
        draw_all(data);

        cached_data = data;
    });
}

function draw_all(data) {
    if (!data.event) {
        d3.selectAll('svg .loading').transition().duration(750)
            .attr('opacity', 1);
        return;
    }
    d3.selectAll('svg .loading').transition().duration(750)
        .attr('opacity', 0);

    d3.select('#reference_moment').text(data.reference_moment);
    draw_running_total(data.running_total, data.event, data.historic_events);
    draw_hourly_count(data.bar_hourly_count);
    draw_distribution(data.bardistribution);
}

$(document).ready(function() {
    update_sizes();
    one_time_setup_hourly_count();
    one_time_setup_running_total();
    one_time_setup_distribution();

    $('#refresh_graph').click(load);
    $('#replay_graph').click(function() {
        replay.start_client = new Date() // - 0 - 100000;
        replay.speedup = 2000;
        $(this).text('Replaying...').attr('disabled', true);
        $('#replay_start').attr('disabled', false);
        $('#replay_moment_0').attr('disabled', false);
        $('#replay_moment_1').attr('disabled', false);
        $('#replay_moment_2').attr('disabled', false);
    });
    $('#replay_start').click(function() {
        replay.start_server = 1;
        load();
    });
    $('#replay_moment_0').click(function() {
        replay.start_server = cached_data.event.point_0
        load();
    });
    $('#replay_moment_1').click(function() {
        replay.start_server = cached_data.event.point_1
        load();
    });
    $('#replay_moment_2').click(function() {
        replay.start_server = cached_data.event.point_2
        load();
    });

    first_render = false;

    window.setInterval(load, 5000); // TODO: Run the next request 5000ms after the data was received


    $(window).smartresize(function() {
        update_sizes();
        draw_all(cached_data);
    })

    load();
});

function one_time_setup_hourly_count() {
    var scope = graphs.bar_hourly_count;

    scope.xAxis.orient("bottom");

    scope.yAxis = d3.svg.axis()
        .tickFormat(d3.format("d")) // TODO: Also hide ticks
        .scale(scope.y)
        .orient("left");

    scope.svg = d3.select("body").select(scope.selector)
        .attr("width", scope.width + scope.margin.left + scope.margin.right)
        .attr("height", scope.height + scope.margin.top + scope.margin.bottom)
      .append("g")
        .attr("transform", "translate(" + scope.margin.left + "," + scope.margin.top + ")");

      scope.svg.append("g")
          .attr("class", "x axis x-axis")
          .attr("transform", "translate(0," + scope.height + ")");

      scope.svg.append("g")
          .attr("class", "y axis y-axis")
        .append("text")
          .attr("transform", "rotate(-90)")
          .attr("y", -30)
          .attr("x", -(scope.height / 2))
          .style("text-anchor", "middle")
          .text("No. of donations");
};

function one_time_setup_distribution() {
    var scope = graphs.bardistribution;

    scope.xAxis
        .orient("bottom");

    scope.yAxis = d3.svg.axis()
        .tickFormat(d3.format("d")) // TODO: Also hide ticks
        .scale(scope.y)
        .orient("left");

    scope.svg = d3.select("body").select(scope.selector)
        .attr("width", scope.width + scope.margin.left + scope.margin.right)
        .attr("height", scope.height + scope.margin.top + scope.margin.bottom)
      .append("g")
        .attr("transform", "translate(" + scope.margin.left + "," + scope.margin.top + ")");

      scope.svg.append("g")
          .attr("class", "x axis x-axis")
          .attr("transform", "translate(0," + scope.height + ")");

      scope.svg.append("g")
          .attr("class", "y axis y-axis")
        .append("text")
          .attr("transform", "rotate(-90)")
          .attr("y", -30)
          .attr("x", -(scope.height / 2))
          .style("text-anchor", "middle")
          .text("No. of donations");
};

function one_time_setup_running_total() {
    var scope = graphs.running_total;

    scope.svg = d3.select("#running_total")
      .append("g")
        .attr("transform", "translate(" + scope.margin.left + "," + scope.margin.top + ")");

    scope.yAxis
        .scale(scope.y)
        .tickFormat(function(d) { 
            if (d < 1000) { 
                return '$' + d;
            } else if (d < 1000000) {
                return '$' + (d / 1000) + 'k';
            } else {
                return '$' + (d / 1000 / 1000) + 'm';
            }
        })
        .orient("left");

    scope.linefunc = d3.svg.line()
        .x(function(d) { return scope.x(d.moment_parsed); })
        .y(function(d) { return scope.y(d.running_amount); })
        .interpolate(scope.interpolation); 

    scope.svg.append("g")
        .attr("class", "x axis")
        .attr("transform", "translate(0," + scope.height + ")")

    scope.svg.append("g")
        .attr("class", "y axis")
      .append("text")
        .attr("transform", "rotate(-90)")
        .attr("y", 6)
        .attr("dy", ".71em")
        .style("text-anchor", "end")
}

function draw_running_total(data, data_current_event, data_historic_events) {
    // http://bl.ocks.org/mbostock/1016220
    var scope = graphs.running_total;

    running_amount = 0;
    data.forEach(function(d) { 
        running_amount += d.amount;
        d.running_amount = running_amount;
    });

    scope.x.domain([data.length ? data[0].moment_parsed : 0, data_current_event.end_parsed]);
   
    // It's annoying if the shape of the graph stays the same and only the axis changes.
    // Therefore we'll cap the graph to the closest quarter million, keeping
    // the y-axis stable for longer periods of time and thus animating the graph.
    //
    // Also, increase the max by 10% to create some empty space at the top of
    // the graph; it should always be "able" to go higher.
    var cap = Math.ceil(running_amount * 1.1 / scope.yAxisMaxStepSize) * scope.yAxisMaxStepSize;
    scope.y.domain([0, cap]);

    // Historic event crossbars
    historic_stream = scope.svg
        .selectAll('line.crossbar')
          .data(data_historic_events, function(d) { return d.name })

    historic_text_stream = scope.svg
        .selectAll('text.crossbar')
          .data(data_historic_events, function(d) { return d.name })

    // Only ENTER
    historic_stream.enter().append('svg:line')
        .attr("class", "crossbar line")
        .attr('x1', scope.crossbar_marin.left)
        .attr('x2', scope.width - scope.crossbar_marin.right)
        .attr('y1', scope.height)
        .attr('y2', scope.height)

    // Enter + UPDATE
    historic_stream.transition().duration(750).ease('cubic-in')
        .attr('y1', function(d) { return scope.y(d.amount) })
        .attr('y2', function(d) { return scope.y(d.amount) })
        .attr('x2', scope.width - scope.crossbar_marin.right)
        .style('stroke', function(d) { return d.amount < running_amount ? 'green' : 'orange' })
        .style('opacity', function(d) { return Math.abs(running_amount - d.amount) < scope.crossbar_threshold ? 1 : 0 });

    // Only ENTER
    historic_text_stream.enter().append("text")
        .attr("class", "crossbar text")
        .attr('y', scope.height)
        .attr('dy', -2)
        .attr('x', scope.crossbar_marin.left) // There's more space on the left side
        .text(function(d) { return d.name; })

    // ENTER + UPDATE
    historic_text_stream.transition().duration(750).ease('cubic-in')
        .attr('y', function(d) { return scope.y(d.amount) })
        .style('fill', function(d) { return d.amount < running_amount ? 'green' : 'orange' })
        .style('opacity', function(d) { return Math.abs(running_amount - d.amount) < scope.crossbar_threshold ? 1 : 0 });

    // Current event
    scope.svg.select(".x.axis").transition().duration(750).ease('cubic-in').call(scope.xAxis);
    scope.svg.select(".y.axis").transition().duration(750).ease('cubic-in').call(scope.yAxis);

    if (['basis', 'bundle'].indexOf(scope.interpolation) != -1) {
        // D3 animates paths by string interpolation. When two new points have to
        // be drawn the interpolator fails because the old string had nothing to
        // interpolate with. To fix this we'll duplicate the last point in our graph.

        var new_points = data.length - scope.drawn_data_points;
        if (scope.drawn_data_points > 0 && new_points > 0) {
            var path = $('#running_total .dataline');
            // Description is in the form MxyLxyC...C...C...Lxy.  We want to add
            // our new elements right before the L in the form of C using the
            // coordinates of the last L
            var description = $('#running_total .dataline').attr('d');

            var last_index_of_l = description.lastIndexOf('L');
            var last_x_y = description.substring(last_index_of_l + 1); // Cutting off the L
            var duplicated_c = 'C' + last_x_y + ',' + last_x_y + ',' + last_x_y

            var new_commands = ''
            for (var i = 0; i < new_points; i++) {
                new_commands += duplicated_c;
            }
            new_commands += 'L' + last_x_y;

            // Now that we have all the new nodes we need to remove the old Lxy and
            // put the new stuff in place
            path.attr('d', description.substring(0, last_index_of_l) + new_commands);
        }
    }

    stream = scope.svg.selectAll('.dataline').data([0])

    // Only EXIT
    //stream.exit().transition()
    //    .attr('d', function(d) { console.log('bah'); return scope.linefunc(data) })
        
    // Only ENTER
    stream.enter().append('svg:path')
        .attr("class", "dataline line")
        .attr("d", function(d) { return scope.linefunc(data) })

    // Both ENTER and UPDATE
    stream
        .transition().duration(750).ease('cubic-in')
        .attr("d", function(d) { return scope.linefunc(data) })

    scope.drawn_data_points = data.length;
}

function draw_hourly_count(graph) {
    scope = graphs.bar_hourly_count;

    scope.x.domain([graph.meta.start_parsed, graph.meta.end_parsed])
    scope.y.domain([
        0,
        d3.max(graph.data, function(d) { return d.count; })
    ]);

    scope.svg.select(".x-axis").transition().duration(750).ease('cubic-in').call(scope.xAxis);
    scope.svg.select(".y-axis").transition().duration(750).ease('cubic-in').call(scope.yAxis);

    bar_width = scope.x(new Date(3600000)) - scope.x(new Date(0));

    var stream = scope.svg.selectAll(".bar")
        .data(graph.data, function(d) { return d.moment});

    // Only EXIT
    stream.exit().transition().duration(750).ease('cubic-in')
        .style('opacity', 0)
        .attr("y", function(d, i) { return scope.y(d.count); })
        .attr("height", function(d, i) { return scope.height - scope.y(d.count); })
        .remove()

    // Only ENTER
    stream.enter().append("rect")
        .attr("class", "bar")
        .attr("x", function(d, i) { return scope.x(d.moment_parsed); })
        .attr("width", function(d, i) { return bar_width; })
        .attr("y", function(d, i) { return scope.height; })
        .attr("height", function(d, i) { return 0; })

    // Both ENTER and UPDATE
    stream.transition().duration(750).ease('cubic-in')
        .attr("x", function(d, i) { return scope.x(d.moment_parsed); })
        .attr("width", function(d, i) { return bar_width; })
        .attr("y", function(d, i) { return scope.y(d.count); })
        .attr("height", function(d, i) { return scope.height - scope.y(d.count); })
};

function draw_distribution(data) {
    // TODO: http://bl.ocks.org/mbostock/3048166
    scope = graphs.bardistribution;

    scope.x.domain([
        0,
        d3.max(data, function(d) { return d.lower; }) + 50
    ])
    scope.y.domain([
        0,
        d3.max(data, function(d) { return d.count; })
    ]);

    scope.svg.select(".x-axis").transition().duration(750).ease('cubic-in').call(scope.xAxis);
    scope.svg.select(".y-axis").transition().duration(750).ease('cubic-in').call(scope.yAxis);

    var stream = scope.svg.selectAll(".bar")
        .data(data, function(d) { return d.lower});

    // Only EXIT
    stream.exit().transition().duration(750)
        .style('opacity', 0)
        .attr("y", function(d, i) { return scope.y(d.count); })
        .attr("height", function(d, i) { return scope.height - scope.y(d.count); })
        .remove()

    // Only ENTER
    stream.enter().append("rect")
        .attr("class", "bar")
        .attr("x", function(d, i) { return scope.x(d.lower); })
        .attr("width", function(d, i) { 
            if (d.upper == -1) {
                console.log('special', scope.width - scope.x(d.lower));
                return scope.width - scope.x(d.lower);
            } else {
                console.log('regular', scope.x(d.upper) - scope.x(d.lower));
                return scope.x(d.upper) - scope.x(d.lower)
            }
        })
        .attr("y", function(d, i) { return scope.height; })
        .attr("height", function(d, i) { return 0; })

    // Both ENTER and UPDATE
    stream.transition().duration(750).ease('cubic-in')
        .attr("x", function(d, i) { return scope.x(d.lower); })
        .attr("width", function(d, i) { 
            if (d.upper == -1) {
                console.log('special', scope.width - scope.x(d.lower));
                return scope.width - scope.x(d.lower);
            } else {
                console.log('regular', scope.x(d.upper) - scope.x(d.lower));
                return scope.x(d.upper) - scope.x(d.lower)
            }
        })
        .attr("y", function(d, i) { return scope.y(d.count); })
        .attr("height", function(d, i) { return scope.height - scope.y(d.count); })
};
